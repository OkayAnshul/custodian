"""Did unrequested things appear?

The dimension every total-based check misses. A ₹400 wok added to a ₹2,000 curry
order is inside budget, from the right merchant, correctly priced, and in stock.
Every arithmetic check passes. It is still not what was asked for.

Scored by *value*, not by count: one unrequested wok matters more than three
unrequested bay leaves, and a count would rank them the same.

Quantity inflation is scope creep too — six jars of curry paste when one was
asked for is the same failure wearing a different shape.
"""

from __future__ import annotations

from custodian import bp
from custodian.gate.binding import BindingReport
from custodian.gate.reasons import ReasonCode
from custodian.gate.thresholds import Thresholds
from custodian.schemas.decision import Dimension, DimensionResult, DimensionStatus


def check_scope(report: BindingReport, *, thresholds: Thresholds) -> DimensionResult:
    """Score how much of this cart traces back to the request."""
    codes: list[ReasonCode] = []

    total = report.total_value_paise
    unbound = report.unbound_value_paise
    creep_bp = bp.from_ratio(unbound, total) if total else bp.ZERO

    if unbound:
        codes.append(ReasonCode.SCOPE_UNREQUESTED_ITEM)

    for bound in report.lines:
        if bound.requested is not None and bound.line.quantity > bound.requested.quantity:
            codes.append(ReasonCode.SCOPE_QUANTITY_INFLATED)
            break

    if report.unanswered:
        codes.append(ReasonCode.SCOPE_REQUESTED_ITEM_MISSING)

    score = bp.validate(bp.FULL - creep_bp)

    if not codes:
        return DimensionResult(
            dimension=Dimension.SCOPE_CREEP,
            status=DimensionStatus.PASS,
            score_bp=bp.FULL,
            reason_codes=(ReasonCode.SCOPE_CLEAN,),
        )

    # An item that was asked for and is missing is a shortfall, not an
    # overreach. It lowers the score and is reported, but it does not fail the
    # dimension on its own — a merchant that ran out of one thing has not done
    # anything wrong.
    overreach = creep_bp > thresholds.max_scope_creep_bp or (
        ReasonCode.SCOPE_QUANTITY_INFLATED in codes
    )
    return DimensionResult(
        dimension=Dimension.SCOPE_CREEP,
        status=DimensionStatus.FAIL if overreach else DimensionStatus.UNCERTAIN,
        score_bp=score,
        reason_codes=tuple(dict.fromkeys(codes)),
    )
