"""Does this item preserve what was asked for?

The one component that is not plumbing. Scoring runs over attribute
decomposition — base identity first, then form — rather than lexical similarity,
for the reason ADR-007 gives: Jaccard scores "coconut milk → coconut cream" and
"coconut milk → almond milk" identically at 0.3333, so the primitive named in the
source document cannot decide the source document's own flagship example.

Resolution order, and what each outcome means:

    base differs, no recorded relationship  -> deterministic fail
    base differs, listed in base_equivalence -> that score
    base same, form same                     -> exact
    base same, form pair listed              -> that score
    base same, form pair unlisted            -> escalate
    either attribute UNKNOWN                 -> escalate

Two scores combine by **minimum**, not by average. A substitution is only as
faithful as its weakest attribute, and averaging would let a perfect base
identity carry an incompatible form past the threshold.

An unlisted pair escalates rather than scoring zero. Not judged and judged badly
are different states, and collapsing them is how a gate becomes confidently
wrong about something nobody ever considered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from custodian.gate.reasons import ReasonCode
from custodian.gate.thresholds import Thresholds
from custodian.schemas.catalog import UNKNOWN, CatalogItem
from custodian.schemas.intent import RequestedItem, SubstitutionPolicy


@dataclass(frozen=True, slots=True)
class SubstitutionTables:
    """The hand-authored compatibility judgments, as an immutable value.

    Extracted from the lexicon rather than read inside ``decide()``: the tables
    are an *input* to a decision, so a decision stays reproducible only if the
    tables it used can be identified. ``version`` is asserted against the
    snapshot's ``lexicon_version`` on replay.
    """

    version: str
    base_scores: Mapping[tuple[str, str], int]
    form_scores: Mapping[tuple[str, str], int]

    @classmethod
    def from_taxonomy(cls, taxonomy) -> "SubstitutionTables":
        return cls(
            version=taxonomy.lexicon_version,
            base_scores=dict(taxonomy._base_scores),
            form_scores=dict(taxonomy._form_scores),
        )

    def base(self, left: str, right: str) -> int | None:
        if left == right:
            return 10_000
        if UNKNOWN in (left, right):
            return None
        return self.base_scores.get(tuple(sorted((left, right))))

    def form(self, left: str, right: str) -> int | None:
        if left == right:
            return 10_000
        if UNKNOWN in (left, right):
            return None
        return self.form_scores.get(tuple(sorted((left, right))))


@dataclass(frozen=True, slots=True)
class Assessment:
    """How faithfully one catalog item stands in for one requested item."""

    score_bp: int
    reason_codes: tuple[ReasonCode, ...]
    #: Deterministic logic could not settle this. It needs a recorded verdict,
    #: and without one the decision holds rather than guessing.
    needs_escalation: bool = False
    #: A hard violation: the substitution is refused regardless of score.
    blocked: bool = False


def assess(
    requested: RequestedItem,
    item: CatalogItem,
    *,
    policy: SubstitutionPolicy,
    tables: SubstitutionTables,
    thresholds: Thresholds,
) -> Assessment:
    """Score one candidate substitution."""
    base_score = tables.base(requested.base, item.base)
    identical_base = requested.base == item.base

    # An attribute the taxonomy could not place is not a mismatch — it is an
    # absence of information, and the honest response is to ask.
    if UNKNOWN in (requested.base, item.base):
        return Assessment(
            score_bp=thresholds.substitution_unfaithful_bp,
            reason_codes=(ReasonCode.SUBST_BASE_UNKNOWN,),
            needs_escalation=True,
        )

    if base_score is None:
        # Different identities with no recorded relationship. This is the
        # coconut-milk-to-almond-milk case, decided here by arithmetic and
        # without a model.
        #
        # Blocking, and under its own code. SUBST_BASE_CHANGED also fires for a
        # *permitted* equivalence (sunflower oil for groundnut oil), so making
        # that code blocking would refuse legitimate swaps. "Different
        # ingredient, no recorded relationship" is a distinct claim and gets a
        # distinct code. See BROKE.md 007.
        return Assessment(
            score_bp=0,
            reason_codes=(ReasonCode.SUBST_BASE_UNRELATED,),
            blocked=True,
        )

    if not identical_base and policy is not SubstitutionPolicy.EQUIVALENT:
        # The human restricted substitutions to the same base. A swap can be
        # perfectly reasonable and still be refused, because the policy is the
        # human's instruction rather than the gate's opinion.
        return Assessment(
            score_bp=base_score,
            reason_codes=(ReasonCode.SUBST_BASE_CHANGED, ReasonCode.SUBST_POLICY_FORBIDS),
            blocked=True,
        )

    form_score = tables.form(requested.form, item.form)
    identical_form = requested.form == item.form

    if policy is SubstitutionPolicy.EXACT_ONLY and not (identical_base and identical_form):
        return Assessment(
            score_bp=min(base_score, form_score if form_score is not None else 0),
            reason_codes=(ReasonCode.SUBST_POLICY_FORBIDS,),
            blocked=True,
        )

    if identical_base and identical_form:
        return Assessment(score_bp=10_000, reason_codes=(ReasonCode.SUBST_EXACT,))

    if form_score is None:
        return Assessment(
            score_bp=thresholds.substitution_unfaithful_bp,
            reason_codes=(ReasonCode.SUBST_FORM_UNLISTED,),
            needs_escalation=True,
        )

    # Weakest attribute governs. A perfect base cannot carry a bad form.
    score = min(base_score, form_score)
    codes: list[ReasonCode] = []
    if not identical_base:
        codes.append(ReasonCode.SUBST_BASE_CHANGED)
    codes.append(
        ReasonCode.SUBST_FORM_COMPATIBLE
        if form_score >= thresholds.substitution_faithful_bp
        else ReasonCode.SUBST_FORM_INCOMPATIBLE
    )

    escalate = (
        thresholds.substitution_unfaithful_bp < score < thresholds.substitution_faithful_bp
    )
    return Assessment(score_bp=score, reason_codes=tuple(codes), needs_escalation=escalate)
