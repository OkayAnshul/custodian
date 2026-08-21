"""Content-addressed storage for the evidence a decision was made from.

A replayable decision has to name every input it used, but writing the whole
catalog snapshot into each ledger row would copy seventy items per decision and
make the chain unreadable. Artifacts are stored once under their own content
hash and referenced by it.

Content addressing gives immutability for free: the key *is* the hash of the
body, so an altered artifact no longer answers to the name a decision recorded.
There is no update path because there is nothing an update could mean.

Snapshots are stored separately from decision inputs and referenced by ``$ref``.
One ingest serves a whole corpus run, so the catalog is written once rather than
a hundred and twenty times.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Self

from custodian.canonical import canonical_hash, canonical_json
from custodian.clock import utc_now
from custodian.gate.thresholds import Thresholds
from custodian.schemas.catalog import CatalogSnapshot
from custodian.schemas.decision_input import DecisionInput

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    digest    TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    body      TEXT NOT NULL,
    stored_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS artifacts_immutable_update
BEFORE UPDATE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are content-addressed: UPDATE refused');
END;
"""

#: Marker for a snapshot lifted out of a decision input.
REF = "$ref"


class ArtifactMissing(KeyError):
    """A decision referenced evidence that is not in the store."""


class ArtifactStore:
    """Immutable, content-addressed evidence."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        #: See Ledger — one connection, several server threads.
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: str | Path) -> Self:
        conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return cls(conn)

    @classmethod
    def in_memory(cls) -> Self:
        return cls(sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False))

    def close(self) -> None:
        self._conn.close()

    # --- primitives --------------------------------------------------------

    def put(self, body: dict[str, Any], *, kind: str, digest: str | None = None) -> str:
        """Store one artifact and return its digest. Idempotent by construction.

        ``digest`` may be supplied when the artifact already has a canonical
        identity that is not simply the hash of its serialised body — a catalog
        snapshot excludes ``snapshot_id`` from its digest, because that id is
        *derived* from the digest and including it would be self-referential.
        Passing it here keeps one artifact under one name.
        """
        digest = digest or canonical_hash(body)
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO artifacts (digest, kind, body, stored_at)"
                " VALUES (?, ?, ?, ?)",
                (digest, kind, canonical_json(body), utc_now()),
            )
        return digest

    def get(self, digest: str) -> dict[str, Any]:
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM artifacts WHERE digest = ?", (digest,)
            ).fetchone()
        if row is None:
            raise ArtifactMissing(f"no artifact {digest[:16]}… in the store")
        return json.loads(row["body"])

    def __len__(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) AS n FROM artifacts").fetchone()["n"]

    # --- decision inputs ---------------------------------------------------

    def put_snapshot(self, snapshot: CatalogSnapshot) -> str:
        """Store a snapshot under its own content digest, not its serialised hash."""
        return self.put(snapshot.canonical(), kind="catalog_snapshot", digest=snapshot.digest())

    def put_input(self, inp: DecisionInput) -> str:
        """Store a decision input, lifting the snapshot out by reference."""
        self.put_snapshot(inp.snapshot)
        body = inp.canonical()
        body["snapshot"] = {REF: inp.snapshot.digest()}
        return self.put(body, kind="decision_input")

    def get_input(self, digest: str) -> DecisionInput:
        """Reconstruct a decision input exactly as it was recorded."""
        body = self.get(digest)
        reference = body.get("snapshot", {})
        if isinstance(reference, dict) and REF in reference:
            body["snapshot"] = self.get(reference[REF])
        return DecisionInput.model_validate(body)

    def put_thresholds(self, thresholds: Thresholds) -> str:
        return self.put(thresholds.canonical(), kind="thresholds")
