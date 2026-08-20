"""Everything ``decide()`` is allowed to see.

Bundling the inputs into one object rather than passing six arguments buys three
things that matter more than the ergonomics.

**Replay becomes trivial.** One object is hashed and recorded; replay loads it
and calls ``decide()``. There is no chance of reconstructing five of six inputs
correctly and the sixth from somewhere else.

**The purity boundary becomes visible.** If it is not on this object,
``decide()`` cannot use it. That includes the clock: ``evaluated_at`` is an
input, so snapshot staleness and mandate expiry are computed by comparing two
recorded values rather than by reading the time (ADR-010).

**The model's position becomes structural.** ``semantic_verdicts`` are recorded
results sitting alongside the catalog and the mandate — inputs to a decision,
not an authority over it. ``decide()`` has no client to call even if it wanted one.
"""

from __future__ import annotations

from custodian.canonical import canonical_hash
from custodian.gate.thresholds import Thresholds
from custodian.schemas.cart import Cart
from custodian.schemas.catalog import CatalogSnapshot
from custodian.schemas.decision import Outcome
from custodian.schemas.intent import Intent
from custodian.schemas.mandate import Mandate
from custodian.schemas.types import Contract, Digest, Identifier, Timestamp
from custodian.schemas.verdict import SemanticVerdict


class DecisionInput(Contract):
    """The complete, self-contained input to one gate decision."""

    request_id: Identifier

    #: The moment to evaluate at. Supplied, never read from a clock.
    evaluated_at: Timestamp

    intent: Intent
    cart: Cart
    snapshot: CatalogSnapshot
    mandate: Mandate

    #: Recorded model output for the lines the deterministic layer escalated.
    #: Empty is normal and means nothing needed escalating.
    semantic_verdicts: tuple[SemanticVerdict, ...] = ()

    thresholds: Thresholds

    def digest(self) -> Digest:
        """Content hash of the whole input. A replay proves it used this."""
        return canonical_hash(self.canonical())

    def verdict_for(self, cart_line_id: str) -> SemanticVerdict | None:
        for verdict in self.semantic_verdicts:
            if verdict.cart_line_id == cart_line_id:
                return verdict
        return None
