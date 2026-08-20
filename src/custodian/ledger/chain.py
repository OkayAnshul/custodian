"""Append-only, hash-chained evidence ledger.

This is not logging. It is the record a dispute is resolved from, and the input
a decision is replayed from, so three properties are enforced mechanically
rather than by convention:

**Append-only at the storage layer.** SQLite triggers abort any ``UPDATE`` or
``DELETE`` against the table. A convention that "we only ever insert" is not
evidence; a database that refuses to mutate is.

**Observed and inferred are separated in every payload.** ``observed`` is what
the system saw — a catalog price, a model's returned verdict, a gateway
response. ``inferred`` is what the system concluded from it. Blurring the two is
how an audit trail becomes an opinion. This is the discipline the problem
statement takes from Voyager's watchdog, made structural: the envelope is
validated on append, so it cannot be skipped under time pressure.

**Composite hashes cover a structure, not a concatenation.** See
``custodian.canonical`` for why.

``ts`` is hashed — a timestamp that can be altered undetectably is not
tamper-evident — but it is deliberately *not* an input to ``gate.decide``.
Recording time and deciding on time are different things.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Self

from custodian.canonical import GENESIS_HASH, canonical_hash, canonical_json, is_hash


class EventType(StrEnum):
    """Every kind of thing worth recording. Closed set — unknown types abort."""

    INTENT_RECEIVED = "INTENT_RECEIVED"
    SNAPSHOT_TAKEN = "SNAPSHOT_TAKEN"
    SEMANTIC_VERDICT = "SEMANTIC_VERDICT"
    DECISION_MADE = "DECISION_MADE"
    RECONFIRM_REQUESTED = "RECONFIRM_REQUESTED"
    RECONFIRM_GRANTED = "RECONFIRM_GRANTED"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_SETTLED = "PAYMENT_SETTLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class LedgerError(RuntimeError):
    """Raised when an append would violate a ledger invariant."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL,
    ts         TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_ledger_request ON ledger(request_id, seq);

-- Append-only, enforced by the database rather than by discipline.
CREATE TRIGGER IF NOT EXISTS ledger_immutable_update
BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS ledger_immutable_delete
BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: DELETE refused');
END;
"""


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """One immutable link in the chain."""

    seq: int
    event_id: str
    request_id: str
    ts: str
    event_type: EventType
    payload: dict[str, Any]
    prev_hash: str
    hash: str

    @property
    def observed(self) -> dict[str, Any]:
        """What the system saw."""
        return self.payload["observed"]

    @property
    def inferred(self) -> dict[str, Any]:
        """What the system concluded. Never mistake this for evidence."""
        return self.payload["inferred"]


def compute_hash(
    *,
    prev_hash: str,
    event_id: str,
    request_id: str,
    ts: str,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    """The chain link. Hashes a structure, so no field boundary is ambiguous."""
    return canonical_hash(
        {
            "prev_hash": prev_hash,
            "event_id": event_id,
            "request_id": request_id,
            "ts": ts,
            "event_type": str(event_type),
            "payload": payload,
        }
    )


def _envelope(observed: dict[str, Any], inferred: dict[str, Any] | None) -> dict[str, Any]:
    """Build and validate the observed/inferred payload envelope."""
    if not isinstance(observed, dict):
        raise LedgerError(f"observed must be a dict, got {type(observed).__name__}")
    if inferred is not None and not isinstance(inferred, dict):
        raise LedgerError(f"inferred must be a dict, got {type(inferred).__name__}")
    return {"observed": observed, "inferred": inferred if inferred is not None else {}}


class Ledger:
    """A hash-chained event log backed by SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    @classmethod
    def open(cls, path: str | Path) -> Self:
        """Open (or create) a ledger file. WAL mode for concurrent readers."""
        conn = sqlite3.connect(str(path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return cls(conn)

    @classmethod
    def in_memory(cls) -> Self:
        """An ephemeral ledger, for tests."""
        return cls(sqlite3.connect(":memory:", isolation_level=None))

    def close(self) -> None:
        self._conn.close()

    def head(self) -> str:
        """Hash of the most recent event, or ``GENESIS_HASH`` if empty."""
        row = self._conn.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        return row["hash"] if row else GENESIS_HASH

    def append(
        self,
        event_type: EventType,
        request_id: str,
        *,
        observed: dict[str, Any],
        inferred: dict[str, Any] | None = None,
        ts: str | None = None,
        event_id: str | None = None,
    ) -> LedgerEvent:
        """Append one event, chained to the current head.

        ``ts`` and ``event_id`` are injectable so tests can produce a
        byte-identical chain; in production both default to real values.
        """
        if not isinstance(event_type, EventType):
            raise LedgerError(f"unknown event type: {event_type!r}")
        if not request_id:
            raise LedgerError("request_id is required — an event that correlates to nothing is not evidence")

        payload = _envelope(observed, inferred)
        canonical_json(payload)  # fail here, not after the transaction opens
        resolved_ts = ts or datetime.now(timezone.utc).isoformat()
        resolved_id = event_id or str(uuid.uuid4())

        # IMMEDIATE takes the write lock up front, so reading the head and
        # writing the successor cannot interleave with another appender and
        # fork the chain.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            prev_hash = self.head()
            digest = compute_hash(
                prev_hash=prev_hash,
                event_id=resolved_id,
                request_id=request_id,
                ts=resolved_ts,
                event_type=event_type,
                payload=payload,
            )
            cursor = self._conn.execute(
                "INSERT INTO ledger (event_id, request_id, ts, event_type, payload, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    resolved_id,
                    request_id,
                    resolved_ts,
                    str(event_type),
                    canonical_json(payload),
                    prev_hash,
                    digest,
                ),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        return LedgerEvent(
            seq=cursor.lastrowid,
            event_id=resolved_id,
            request_id=request_id,
            ts=resolved_ts,
            event_type=event_type,
            payload=payload,
            prev_hash=prev_hash,
            hash=digest,
        )

    def read(self, request_id: str) -> list[LedgerEvent]:
        """Every event for one request, in order."""
        rows = self._conn.execute(
            "SELECT * FROM ledger WHERE request_id = ? ORDER BY seq", (request_id,)
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def scan(self) -> Iterator[LedgerEvent]:
        """The whole chain, oldest first."""
        for row in self._conn.execute("SELECT * FROM ledger ORDER BY seq"):
            yield _row_to_event(row)

    def __len__(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM ledger").fetchone()["n"]


def _row_to_event(row: sqlite3.Row) -> LedgerEvent:
    import json

    return LedgerEvent(
        seq=row["seq"],
        event_id=row["event_id"],
        request_id=row["request_id"],
        ts=row["ts"],
        event_type=EventType(row["event_type"]),
        payload=json.loads(row["payload"]),
        prev_hash=row["prev_hash"],
        hash=row["hash"],
    )
