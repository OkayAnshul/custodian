"""What the gate concluded, and everything needed to defend it.

Alignment is not one number. It decomposes into dimensions that are scored
separately, each carrying its own reason codes, and the overall figure is a
weighted aggregate of those — never an opaque score handed down by a model.
"Why did Custodian hold this order?" is answered by reading the dimensions.

One invariant is enforced here rather than tested for: a decision that approves
while carrying a blocking reason code cannot be constructed. If the arithmetic
says the cart exceeds the mandate, no downstream bug can produce an APPROVE
holding that code — the object will not build.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from custodian.gate.reasons import BLOCKING, ReasonCode, explain
from custodian.schemas.types import Contract, Digest, Identifier, Paise, ScoreBp, Timestamp


class Outcome(StrEnum):
    """The three-way gate.

    ``HOLD`` is not a soft reject. It routes to re-confirmation, and a
    legitimate purchase held here still completes. Collapsing it into either
    neighbour is what makes a system merchants switch off.
    """

    APPROVE = "APPROVE"
    HOLD = "HOLD"
    REJECT = "REJECT"


class Dimension(StrEnum):
    """The independently scored axes of alignment."""

    PRICE_INTEGRITY = "PRICE_INTEGRITY"
    BUDGET = "BUDGET"
    MERCHANT_SCOPE = "MERCHANT_SCOPE"
    CATEGORY_SCOPE = "CATEGORY_SCOPE"
    MANDATE = "MANDATE"
    SUBSTITUTION = "SUBSTITUTION"
    SCOPE_CREEP = "SCOPE_CREEP"
    SANITIZATION = "SANITIZATION"


class DimensionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    #: Could not be settled with enough confidence. Pushes toward ``HOLD``;
    #: never toward a guess in either direction.
    UNCERTAIN = "UNCERTAIN"


class BindingKind(StrEnum):
    """How a cart line traces back to something the human asked for."""

    EXACT = "EXACT"
    SUBSTITUTION = "SUBSTITUTION"
    BUNDLE_MEMBER = "BUNDLE_MEMBER"
    #: Traces to nothing. The ₹400 wok: within budget, out of scope.
    UNBOUND = "UNBOUND"


class DimensionResult(Contract):
    """One axis, scored and explained."""

    dimension: Dimension
    status: DimensionStatus
    score_bp: ScoreBp
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def _says_why(self) -> "DimensionResult":
        if not self.reason_codes:
            raise ValueError(f"{self.dimension} produced no reason code — a score without a reason is not explainable")
        return self

    @property
    def reason_text(self) -> str:
        """Rendered from the codes. Never model-authored prose."""
        return " ".join(explain(code) for code in self.reason_codes)

    @property
    def blocking_codes(self) -> tuple[ReasonCode, ...]:
        return tuple(code for code in self.reason_codes if code in BLOCKING)


class Binding(Contract):
    """The trace from one cart line to one request line."""

    cart_line_id: Identifier
    requested_line_id: Identifier | None
    kind: BindingKind
    score_bp: ScoreBp
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def _unbound_means_unbound(self) -> "Binding":
        bound = self.requested_line_id is not None
        if bound == (self.kind is BindingKind.UNBOUND):
            raise ValueError(
                f"binding kind {self.kind} disagrees with requested_line_id="
                f"{self.requested_line_id!r}"
            )
        return self


class Decision(Contract):
    """The gate's disposition, with the evidence it rests on."""

    request_id: Identifier
    outcome: Outcome
    evaluated_at: Timestamp

    #: Weighted aggregate across dimensions, and how sure the gate is of it.
    #: Confidence is computed deterministically from coverage and margin — it is
    #: never a model's self-report, which is not a measurement.
    alignment_bp: ScoreBp
    confidence_bp: ScoreBp

    dimensions: tuple[DimensionResult, ...]
    bindings: tuple[Binding, ...]

    #: The gate's own arithmetic over catalog prices. This is the amount that
    #: may be charged. The agent's asserted total is recorded as a claim and is
    #: never what settles.
    verified_total_paise: Paise

    #: What this decision was derived from, so a replay can prove it used the
    #: same inputs.
    snapshot_digest: Digest
    thresholds_version: str = Field(min_length=1, max_length=32)
    thresholds_digest: Digest

    #: Cart lines the deterministic layer could not settle alone.
    escalated_line_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _every_dimension_is_reported(self) -> "Decision":
        reported = [d.dimension for d in self.dimensions]
        if len(reported) != len(set(reported)):
            raise ValueError("a dimension was scored twice")
        if missing := sorted(set(Dimension) - set(reported)):
            raise ValueError(
                f"decision does not report every dimension; missing: {[str(m) for m in missing]}"
            )
        return self

    @model_validator(mode="after")
    def _approval_cannot_carry_a_blocking_violation(self) -> "Decision":
        if self.outcome is not Outcome.APPROVE:
            return self
        if blocking := sorted({str(c) for d in self.dimensions for c in d.blocking_codes}):
            raise ValueError(
                f"APPROVE is unconstructable while a blocking constraint is violated: {blocking}"
            )
        return self

    @model_validator(mode="after")
    def _a_refusal_says_why(self) -> "Decision":
        if self.outcome is Outcome.APPROVE:
            return self
        if all(d.status is DimensionStatus.PASS for d in self.dimensions):
            raise ValueError(f"{self.outcome} with every dimension passing gives the merchant nothing to act on")
        return self

    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        """Every code raised, in dimension order."""
        return tuple(code for d in self.dimensions for code in d.reason_codes)

    @property
    def reason_text(self) -> str:
        return " ".join(d.reason_text for d in self.dimensions if d.status is not DimensionStatus.PASS) or (
            "Every check passed."
        )

    def dimension(self, name: Dimension) -> DimensionResult:
        for result in self.dimensions:
            if result.dimension is name:
                return result
        raise KeyError(name)  # unreachable: _every_dimension_is_reported
