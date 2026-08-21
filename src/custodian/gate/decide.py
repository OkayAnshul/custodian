"""The decision. One pure function.

``decide`` has no clock, no network, no randomness and no dependence on dict
ordering. Given the same ``DecisionInput`` and the same tables it produces the
same bytes, every time, on any machine. That property is not a nicety — it is
the whole of the replay claim, and everything else in this package was shaped to
preserve it.

The model is not called here and cannot be. Where deterministic logic could not
settle a substitution, the model was asked *upstream* and its answer arrives in
``inp.semantic_verdicts`` as a recorded observation, with the same standing as a
catalog price. A verdict that was never obtained is not an error and not a guess:
it lowers confidence, and low confidence holds.

Order matters. Deterministic checks run first and reject on their own authority,
so the semantic scorer never sees a case the arithmetic already settled — see
``escalations``, which returns nothing at all when a hard constraint has failed.
"""

from __future__ import annotations

from custodian import bp
from custodian.gate import confidence as confidence_module
from custodian.gate import deterministic as det
from custodian.gate.binding import BindingReport, bind
from custodian.gate.reasons import BLOCKING, ReasonCode
from custodian.gate.scope import check_scope
from custodian.gate.substitution import SubstitutionTables
from custodian.schemas.decision import (
    Decision,
    Dimension,
    DimensionResult,
    DimensionStatus,
    Outcome,
)
from custodian.schemas.decision_input import DecisionInput
from custodian.schemas.verdict import VerdictLabel


def decide(inp: DecisionInput, *, tables: SubstitutionTables) -> Decision:
    """Evaluate one proposed purchase. Pure."""
    verified_total = det.verified_total_paise(inp.cart, inp.snapshot)

    hard = [
        det.check_price_integrity(
            inp.cart, inp.snapshot, evaluated_at=inp.evaluated_at, thresholds=inp.thresholds
        ),
        det.check_budget(inp.intent, inp.cart, inp.snapshot, verified_total=verified_total),
        det.check_merchant_scope(inp.intent, inp.cart, inp.mandate),
        det.check_category_scope(inp.intent, inp.cart, inp.snapshot),
        det.check_mandate(
            inp.mandate, inp.cart, inp.snapshot,
            verified_total=verified_total, evaluated_at=inp.evaluated_at,
        ),
        det.check_sanitization(inp.cart, inp.snapshot),
    ]

    report = bind(
        inp.intent, inp.cart, inp.snapshot, tables=tables, thresholds=inp.thresholds
    )
    substitution = _substitution_dimension(inp, report)
    scope = check_scope(report, thresholds=inp.thresholds)

    dimensions = tuple(hard) + (substitution, scope)
    alignment = _alignment(dimensions, inp.thresholds)
    confidence = confidence_module.compute(
        report, inp.semantic_verdicts, alignment_bp=alignment, thresholds=inp.thresholds
    )
    outcome, disposition = _outcome(
        dimensions, alignment=alignment, confidence=confidence, thresholds=inp.thresholds
    )

    return Decision(
        request_id=inp.request_id,
        outcome=outcome,
        evaluated_at=inp.evaluated_at,
        alignment_bp=alignment,
        confidence_bp=confidence,
        dimensions=dimensions,
        bindings=report.bindings,
        verified_total_paise=verified_total,
        snapshot_digest=inp.snapshot.digest(),
        thresholds_version=inp.thresholds.version,
        thresholds_digest=inp.thresholds.digest(),
        escalated_line_ids=report.escalated_line_ids,
        disposition_codes=disposition,
    )


def escalations(inp: DecisionInput, *, tables: SubstitutionTables) -> tuple[str, ...]:
    """Cart lines a model must be asked about, before ``decide`` is called.

    Returns nothing when a deterministic check has already failed. That is the
    "the semantic scorer never sees a case the arithmetic settled" guarantee,
    implemented rather than asserted — and it is also the cost argument, since
    a rejected cart costs no tokens at all.
    """
    verified_total = det.verified_total_paise(inp.cart, inp.snapshot)
    settled_by_arithmetic = (
        det.check_price_integrity(
            inp.cart, inp.snapshot, evaluated_at=inp.evaluated_at, thresholds=inp.thresholds
        ),
        det.check_budget(inp.intent, inp.cart, inp.snapshot, verified_total=verified_total),
        det.check_merchant_scope(inp.intent, inp.cart, inp.mandate),
        det.check_category_scope(inp.intent, inp.cart, inp.snapshot),
        det.check_mandate(
            inp.mandate, inp.cart, inp.snapshot,
            verified_total=verified_total, evaluated_at=inp.evaluated_at,
        ),
    )
    if any(result.blocking_codes for result in settled_by_arithmetic):
        return ()

    report = bind(inp.intent, inp.cart, inp.snapshot, tables=tables, thresholds=inp.thresholds)
    return report.escalated_line_ids


# --- dimensions ------------------------------------------------------------

def _substitution_dimension(inp: DecisionInput, report: BindingReport) -> DimensionResult:
    """Aggregate item-level fidelity, weighting by what each line is worth."""
    parts: list[tuple[int, int]] = []
    codes: list[ReasonCode] = []
    blocked = False
    unresolved = False

    for bound in report.lines:
        if bound.assessment is None:
            continue
        assessment = bound.assessment
        weight = max(bound.value_paise, 1)

        if assessment.blocked:
            blocked = True
            codes.extend(assessment.reason_codes)
            parts.append((assessment.score_bp, weight))
            continue

        if not assessment.needs_escalation:
            codes.extend(assessment.reason_codes)
            parts.append((assessment.score_bp, weight))
            continue

        verdict = inp.verdict_for(bound.line.line_id)
        if verdict is None:
            unresolved = True
            codes.append(ReasonCode.SUBST_VERDICT_MISSING)
            parts.append((assessment.score_bp, weight))
        elif verdict.label is VerdictLabel.UNSURE:
            unresolved = True
            codes.append(ReasonCode.SUBST_MODEL_UNSURE)
            parts.append((verdict.score_bp, weight))
        else:
            codes.append(
                ReasonCode.SUBST_MODEL_FAITHFUL
                if verdict.label is VerdictLabel.FAITHFUL
                else ReasonCode.SUBST_MODEL_UNFAITHFUL
            )
            parts.append((verdict.score_bp, weight))

    if not parts:
        return DimensionResult(
            dimension=Dimension.SUBSTITUTION,
            status=DimensionStatus.UNCERTAIN,
            score_bp=bp.ZERO,
            reason_codes=(ReasonCode.SCOPE_UNREQUESTED_ITEM,),
        )

    score = bp.weighted(parts)
    if blocked:
        status = DimensionStatus.FAIL
    elif unresolved:
        status = DimensionStatus.UNCERTAIN
    elif score >= inp.thresholds.substitution_faithful_bp:
        status = DimensionStatus.PASS
    elif score <= inp.thresholds.substitution_unfaithful_bp:
        status = DimensionStatus.FAIL
    else:
        status = DimensionStatus.UNCERTAIN

    return DimensionResult(
        dimension=Dimension.SUBSTITUTION,
        status=status,
        score_bp=score,
        reason_codes=tuple(dict.fromkeys(codes)),
    )


def _alignment(dimensions: tuple[DimensionResult, ...], thresholds) -> int:
    """Weighted aggregate. Never one opaque number handed down by a model."""
    weights = thresholds.weights
    lookup = {
        Dimension.PRICE_INTEGRITY: weights.price_integrity,
        Dimension.BUDGET: weights.budget,
        Dimension.MERCHANT_SCOPE: weights.merchant_scope,
        Dimension.CATEGORY_SCOPE: weights.category_scope,
        Dimension.MANDATE: weights.mandate,
        Dimension.SUBSTITUTION: weights.substitution,
        Dimension.SCOPE_CREEP: weights.scope_creep,
        Dimension.SANITIZATION: weights.sanitization,
    }
    return bp.weighted([(d.score_bp, lookup[d.dimension]) for d in dimensions])


def _outcome(
    dimensions: tuple[DimensionResult, ...], *, alignment: int, confidence: int, thresholds
) -> tuple[Outcome, tuple[ReasonCode, ...]]:
    """The three-way gate.

    Order is the policy. A hard violation rejects regardless of score, because a
    constraint that can be outvoted by a good average is not a constraint. Below
    that, uncertainty routes to ``HOLD`` before either neighbour — a system that
    is confidently wrong is worse than one that asks.
    """
    if any(code in BLOCKING for d in dimensions for code in d.reason_codes):
        return Outcome.REJECT, (ReasonCode.HARD_CONSTRAINT_VIOLATED,)
    if alignment <= thresholds.reject_max_alignment_bp:
        return Outcome.REJECT, (ReasonCode.ALIGNMENT_BELOW_APPROVE_THRESHOLD,)

    # A failed dimension cannot be outvoted by a good average. Without this,
    # an unrequested ₹1,450 wok scores 32% on scope creep, the other seven
    # dimensions carry the weighted mean to 91%, and the order approves — which
    # is the exact failure this system exists to prevent. Weights decide how
    # much a dimension contributes; they do not decide whether a failure counts.
    if any(d.status is DimensionStatus.FAIL for d in dimensions):
        return Outcome.HOLD, ()
    if any(d.status is DimensionStatus.UNCERTAIN for d in dimensions):
        return Outcome.HOLD, ()

    if confidence < thresholds.min_confidence_bp:
        return Outcome.HOLD, (ReasonCode.CONFIDENCE_BELOW_THRESHOLD,)
    if alignment >= thresholds.approve_min_alignment_bp:
        return Outcome.APPROVE, ()
    return Outcome.HOLD, (ReasonCode.ALIGNMENT_BELOW_APPROVE_THRESHOLD,)
