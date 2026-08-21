"""Which requested item does each cart line answer?

Binding is re-derived, never taken on trust. The agent may declare
``satisfies_line_id`` and Custodian reads it as a claim about *which* request a
line is answering — but the *fidelity* of that answer is always recomputed. An
agent that mislabels a line changes what gets scored, not whether it passes.

The distinction the binding step exists to draw is between two failures that a
budget check alone cannot tell apart:

    almond milk offered for coconut milk  -> bound, and unfaithful
    a ₹1,450 wok nobody asked for         -> bound to nothing: scope creep

Both may sit inside budget. Only the second is invisible to every check that
looks at totals. Category proximity separates them: almond milk and coconut milk
are both dairy alternatives, so the almond milk binds and fails on fidelity,
while cookware answers nothing in a curry request and binds to nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from custodian.gate.reasons import ReasonCode
from custodian.gate.substitution import Assessment, SubstitutionTables, assess
from custodian.gate.thresholds import Thresholds
from custodian.money import line_total
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.catalog import UNKNOWN, CatalogSnapshot
from custodian.schemas.decision import Binding, BindingKind
from custodian.schemas.intent import Intent, RequestedItem


@dataclass(frozen=True, slots=True)
class BoundLine:
    """One cart line, with what it answers and how well."""

    line: CartLine
    requested: RequestedItem | None
    assessment: Assessment | None
    #: Catalog value of this line, used to weight scope creep and confidence.
    value_paise: int

    @property
    def bound(self) -> bool:
        return self.requested is not None

    def to_binding(self) -> Binding:
        if self.requested is None or self.assessment is None:
            return Binding(
                cart_line_id=self.line.line_id,
                requested_line_id=None,
                kind=BindingKind.UNBOUND,
                score_bp=0,
                reason_codes=(ReasonCode.SCOPE_UNREQUESTED_ITEM,),
            )
        exact = ReasonCode.SUBST_EXACT in self.assessment.reason_codes
        return Binding(
            cart_line_id=self.line.line_id,
            requested_line_id=self.requested.line_id,
            kind=BindingKind.EXACT if exact else BindingKind.SUBSTITUTION,
            score_bp=self.assessment.score_bp,
            reason_codes=self.assessment.reason_codes,
        )


@dataclass(frozen=True, slots=True)
class BindingReport:
    """The full trace from cart back to request."""

    lines: tuple[BoundLine, ...]
    #: Requested items nothing in the cart answers.
    unanswered: tuple[RequestedItem, ...]

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return tuple(line.to_binding() for line in self.lines)

    @property
    def total_value_paise(self) -> int:
        return sum(line.value_paise for line in self.lines)

    @property
    def unbound_value_paise(self) -> int:
        return sum(line.value_paise for line in self.lines if not line.bound)

    @property
    def escalated_line_ids(self) -> tuple[str, ...]:
        return tuple(
            bound.line.line_id
            for bound in self.lines
            if bound.assessment is not None and bound.assessment.needs_escalation
        )


def bind(
    intent: Intent,
    cart: Cart,
    snapshot: CatalogSnapshot,
    *,
    tables: SubstitutionTables,
    thresholds: Thresholds,
) -> BindingReport:
    """Trace every cart line back to what was asked for."""
    bound_lines: list[BoundLine] = []
    answered: set[str] = set()

    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is None:
            # Not in the catalog at all. The price check rejects on its own
            # authority; here it simply answers nothing.
            bound_lines.append(BoundLine(line=line, requested=None, assessment=None, value_paise=0))
            continue

        value = line_total(item.price_paise, line.quantity)
        candidate = _claimed(intent, line) or _best_candidate(
            intent, item, tables=tables, thresholds=thresholds
        )
        if candidate is None:
            bound_lines.append(BoundLine(line=line, requested=None, assessment=None, value_paise=value))
            continue

        assessment = assess(
            candidate, item,
            policy=intent.substitution_policy, tables=tables, thresholds=thresholds,
        )
        answered.add(candidate.line_id)
        bound_lines.append(
            BoundLine(line=line, requested=candidate, assessment=assessment, value_paise=value)
        )

    unanswered = tuple(
        item for item in intent.requested_items if item.line_id not in answered
    )
    return BindingReport(lines=tuple(bound_lines), unanswered=unanswered)


def _claimed(intent: Intent, line: CartLine) -> RequestedItem | None:
    """The request the agent says this line answers, if it named a real one."""
    if line.satisfies_line_id is None:
        return None
    return intent.find(line.satisfies_line_id)


def _best_candidate(
    intent: Intent,
    item,
    *,
    tables: SubstitutionTables,
    thresholds: Thresholds,
) -> RequestedItem | None:
    """Re-derive which request this item plausibly answers.

    Plausible means: a scored relationship exists, or the categories agree.
    Category is the weaker signal and is what keeps a bad substitute bound —
    almond milk is a wrong answer to "coconut milk", not an answer to nothing.
    """
    best: tuple[int, RequestedItem] | None = None
    for requested in intent.requested_items:
        assessment = assess(
            requested, item,
            policy=intent.substitution_policy, tables=tables, thresholds=thresholds,
        )
        related = (
            assessment.score_bp > 0
            or assessment.needs_escalation
            or (requested.category == item.category and item.category != UNKNOWN)
        )
        if related and (best is None or assessment.score_bp > best[0]):
            best = (assessment.score_bp, requested)
    return best[1] if best else None
