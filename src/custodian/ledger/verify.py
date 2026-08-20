"""Chain integrity verification.

The ledger's claim is tamper-evidence, not tamper-proofing: anyone with write
access to the file can alter a row, and this module is what makes that alteration
visible. It walks the chain and reports the *first* link that fails, because a
single edited byte invalidates every hash after it — reporting all downstream
breaks would bury the actual edit in noise.

Deleting an event needs no separate check: the successor's ``prev_hash`` will no
longer match its predecessor's ``hash``, which ``LINK_MISMATCH`` already catches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from custodian.canonical import GENESIS_HASH
from custodian.ledger.chain import Ledger, compute_hash

BreakKind = Literal["LINK_MISMATCH", "HASH_MISMATCH", "MALFORMED_PAYLOAD"]


@dataclass(frozen=True, slots=True)
class ChainBreak:
    """Where the chain stops being trustworthy, and why."""

    seq: int
    event_id: str
    kind: BreakKind
    expected: str
    actual: str

    def __str__(self) -> str:
        return (
            f"seq={self.seq} event_id={self.event_id} {self.kind}: "
            f"expected {self.expected[:16]}… got {self.actual[:16]}…"
        )


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Outcome of a full-chain walk."""

    ok: bool
    events_checked: int
    head: str
    breaks: list[ChainBreak] = field(default_factory=list)

    def __str__(self) -> str:
        if self.ok:
            return f"chain intact: {self.events_checked} events, head={self.head[:16]}…"
        return f"chain BROKEN after {self.events_checked} events: " + "; ".join(
            str(b) for b in self.breaks
        )


def verify_chain(ledger: Ledger, *, stop_at_first_break: bool = True) -> VerifyResult:
    """Walk the chain from genesis, recomputing every hash."""
    breaks: list[ChainBreak] = []
    expected_prev = GENESIS_HASH
    checked = 0
    head = GENESIS_HASH

    for event in ledger.scan():
        if event.prev_hash != expected_prev:
            breaks.append(
                ChainBreak(
                    seq=event.seq,
                    event_id=event.event_id,
                    kind="LINK_MISMATCH",
                    expected=expected_prev,
                    actual=event.prev_hash,
                )
            )
            if stop_at_first_break:
                break

        if not (isinstance(event.payload, dict) and {"observed", "inferred"} <= event.payload.keys()):
            breaks.append(
                ChainBreak(
                    seq=event.seq,
                    event_id=event.event_id,
                    kind="MALFORMED_PAYLOAD",
                    expected="{observed, inferred}",
                    actual=str(sorted(event.payload))[:64] if isinstance(event.payload, dict) else "not-a-dict",
                )
            )
            if stop_at_first_break:
                break

        recomputed = compute_hash(
            prev_hash=event.prev_hash,
            event_id=event.event_id,
            request_id=event.request_id,
            ts=event.ts,
            event_type=event.event_type,
            payload=event.payload,
        )
        if recomputed != event.hash:
            breaks.append(
                ChainBreak(
                    seq=event.seq,
                    event_id=event.event_id,
                    kind="HASH_MISMATCH",
                    expected=recomputed,
                    actual=event.hash,
                )
            )
            if stop_at_first_break:
                break

        checked += 1
        expected_prev = event.hash
        head = event.hash

    return VerifyResult(ok=not breaks, events_checked=checked, head=head, breaks=breaks)
