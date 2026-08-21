"""Re-derive a recorded decision from its recorded evidence.

The credibility claim, made checkable: take a ledger entry, load the inputs it
names, run the same pure function, and compare bytes. No model is called and
none can be — ``decide()`` has no client, and the model output it uses was
recorded as an observation when the decision was first made.

A mismatch is reported with the fields that differ rather than as a bare
boolean. "The decision does not reproduce" is not useful; "alignment_bp was 9200
and is now 8900, and the thresholds digest changed" points at the cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custodian.canonical import canonical_hash
from custodian.gate.decide import decide
from custodian.gate.substitution import SubstitutionTables
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.store import ArtifactMissing, ArtifactStore
from custodian.schemas.decision import Decision


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Whether a recorded decision reproduces, and what moved if not."""

    request_id: str
    matched: bool
    recorded: Decision | None = None
    recomputed: Decision | None = None
    differences: tuple[str, ...] = ()
    error: str | None = None

    def __str__(self) -> str:
        if self.error:
            return f"{self.request_id}: cannot replay — {self.error}"
        if self.matched:
            return f"{self.request_id}: reproduces exactly ({self.recorded.outcome})"
        return f"{self.request_id}: DIVERGED — " + "; ".join(self.differences)


def replay(
    ledger: Ledger, store: ArtifactStore, request_id: str, *, tables: SubstitutionTables
) -> ReplayResult:
    """Re-run one recorded decision from the evidence the ledger names."""
    events = ledger.read(request_id)
    event = next((e for e in reversed(events) if e.event_type is EventType.DECISION_MADE), None)
    if event is None:
        return ReplayResult(request_id, matched=False, error="no decision recorded")

    try:
        recorded_input = store.get_input(event.observed["input_digest"])
        recorded = Decision.model_validate(store.get(event.inferred["decision_digest"]))
    except (ArtifactMissing, KeyError) as exc:
        return ReplayResult(request_id, matched=False, error=f"evidence unavailable: {exc}")

    if tables.version != event.observed.get("tables_version"):
        return ReplayResult(
            request_id, matched=False, recorded=recorded,
            error=(
                f"lexicon version differs: recorded {event.observed.get('tables_version')!r}, "
                f"loaded {tables.version!r} — the tables are an input, so a different "
                f"lexicon is a different decision"
            ),
        )

    recomputed = decide(recorded_input, tables=tables)
    if canonical_hash(recorded.canonical()) == canonical_hash(recomputed.canonical()):
        return ReplayResult(request_id, matched=True, recorded=recorded, recomputed=recomputed)

    return ReplayResult(
        request_id, matched=False, recorded=recorded, recomputed=recomputed,
        differences=_differences(recorded.canonical(), recomputed.canonical()),
    )


def replay_all(
    ledger: Ledger, store: ArtifactStore, *, tables: SubstitutionTables
) -> tuple[ReplayResult, ...]:
    """Replay every decision in the ledger, oldest first."""
    request_ids = list(
        dict.fromkeys(
            event.request_id for event in ledger.scan()
            if event.event_type is EventType.DECISION_MADE
        )
    )
    return tuple(replay(ledger, store, rid, tables=tables) for rid in request_ids)


def _differences(recorded: dict[str, Any], recomputed: dict[str, Any], path: str = "") -> tuple[str, ...]:
    """Field-level diff, so a mismatch names its cause."""
    found: list[str] = []
    for key in sorted(set(recorded) | set(recomputed)):
        here = f"{path}.{key}" if path else key
        left, right = recorded.get(key), recomputed.get(key)
        if isinstance(left, dict) and isinstance(right, dict):
            found.extend(_differences(left, right, here))
        elif left != right:
            found.append(f"{here}: recorded {left!r} -> recomputed {right!r}")
    return tuple(found[:12])
