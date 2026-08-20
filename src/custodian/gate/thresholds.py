"""The tunable parameters, versioned and hashed.

Two reasons this is a first-class object rather than a handful of constants.

**Replay.** Retuning a threshold on day 12 would otherwise silently change what
every historical decision replays to. The version travels with each decision, so
a replay mismatch can be attributed rather than merely observed.

**The eval is an argument, not a pass rate.** The hold threshold is the dial
that trades false holds against false approvals, and the threshold sweep is the
curve that dial traces. That only works if the dial is a value the harness can
vary — not a number buried in an ``if``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from custodian.canonical import canonical_hash
from custodian.schemas.types import Contract, Digest, Paise, ScoreBp


class DimensionWeights(Contract):
    """Relative weight of each dimension in the overall alignment score.

    Weights are integers whose ratios are all that matter. Substitution carries
    the most because it is the dimension the deterministic layer cannot fully
    settle — the others mostly resolve to pass or fail on their own authority
    and contribute little to a graded score.
    """

    price_integrity: int = Field(default=3, strict=True, ge=0)
    budget: int = Field(default=3, strict=True, ge=0)
    merchant_scope: int = Field(default=2, strict=True, ge=0)
    category_scope: int = Field(default=1, strict=True, ge=0)
    mandate: int = Field(default=3, strict=True, ge=0)
    substitution: int = Field(default=5, strict=True, ge=0)
    scope_creep: int = Field(default=3, strict=True, ge=0)
    sanitization: int = Field(default=2, strict=True, ge=0)


class Thresholds(Contract):
    """Every number the gate's disposition depends on."""

    version: str = Field(min_length=1, max_length=32)

    #: Overall alignment at or above this may approve; at or below
    #: ``reject_max_alignment_bp`` rejects. Between them is where hold lives —
    #: and that band is the whole subject of the threshold sweep.
    approve_min_alignment_bp: ScoreBp = 8_000
    reject_max_alignment_bp: ScoreBp = 4_000

    #: Below this confidence the gate holds regardless of alignment. This is
    #: calibrated abstention: knowing that it does not know.
    min_confidence_bp: ScoreBp = 7_000

    #: Substitution bands (ADR-007). At or above ``faithful`` is settled
    #: deterministically; at or below ``unfaithful`` likewise. Strictly between
    #: them is what escalates to the model — and nothing else does.
    substitution_faithful_bp: ScoreBp = 8_000
    substitution_unfaithful_bp: ScoreBp = 4_000

    #: Share of cart value that may be unaccounted for before scope creep bites.
    max_scope_creep_bp: ScoreBp = 500

    #: Permitted gap between the agent's asserted price and the catalog's.
    #: Zero on purpose: a price is looked up, not estimated, so any difference
    #: means the agent's view is wrong or the claim is false.
    price_tolerance_paise: Paise = 0

    #: How old a catalog snapshot may be at decision time.
    max_snapshot_age_seconds: int = Field(default=900, strict=True, gt=0)

    weights: DimensionWeights = DimensionWeights()

    @model_validator(mode="after")
    def _bands_are_ordered(self) -> "Thresholds":
        if self.reject_max_alignment_bp >= self.approve_min_alignment_bp:
            raise ValueError(
                f"reject band ({self.reject_max_alignment_bp}) overlaps approve band "
                f"({self.approve_min_alignment_bp}) — there would be no room to hold"
            )
        if self.substitution_unfaithful_bp >= self.substitution_faithful_bp:
            raise ValueError(
                f"substitution bands overlap: unfaithful ({self.substitution_unfaithful_bp}) "
                f">= faithful ({self.substitution_faithful_bp}) — nothing could escalate"
            )
        return self

    def digest(self) -> Digest:
        """Content hash, recorded with every decision."""
        return canonical_hash(self.canonical())


#: The starting point. Corpus-driven tuning on the dev split replaces these
#: numbers; until the corpus exists they are stated guesses, and are labelled as
#: such rather than presented as calibrated.
DEFAULT = Thresholds(version="v0-untuned")
