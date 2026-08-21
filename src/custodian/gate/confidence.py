"""How sure is the gate, computed rather than asked for.

Confidence here is never a model's self-report. A model asked "how confident are
you?" produces a number that correlates with fluency rather than with accuracy,
and putting that number in front of the abstention threshold would mean the
system abstains when the model *sounds* unsure. Abstention has to key on
something measurable.

Two measurable things:

**Coverage.** What fraction of the cart's value did deterministic logic settle
by itself? Value settled by a recorded model verdict counts, but for less —
a model answer is real evidence and weaker evidence. Value escalated with no
verdict recorded counts for nothing, because nothing decided it.

**Margin.** How far is the alignment score from the nearest band edge? A cart
scoring 8001 against an 8000 threshold is arithmetically an approval and
practically a coin flip, and saying so is the difference between a calibrated
gate and a confident one.
"""

from __future__ import annotations

from custodian import bp
from custodian.gate.binding import BindingReport
from custodian.gate.thresholds import Thresholds
from custodian.schemas.verdict import SemanticVerdict

#: Weight given to cart value settled by a recorded model verdict, relative to
#: value settled by arithmetic. Not a tuned number — a stated position that a
#: model's answer is worth rather less than a lookup, revisited against the
#: corpus like every other threshold.
VERDICT_EVIDENCE_BP = 7_000

#: Alignment distance beyond which the margin term stops mattering.
MARGIN_WINDOW_BP = 1_500

#: Coverage dominates; margin adjusts.
_COVERAGE_WEIGHT = 3
_MARGIN_WEIGHT = 1


def compute(
    report: BindingReport,
    verdicts: tuple[SemanticVerdict, ...],
    *,
    alignment_bp: int,
    thresholds: Thresholds,
) -> int:
    """Confidence in basis points, from coverage and margin."""
    resolved = {v.cart_line_id for v in verdicts if v.usable}

    settled_value = 0
    verdict_value = 0
    unresolved_value = 0
    for bound in report.lines:
        escalated = bound.assessment is not None and bound.assessment.needs_escalation
        if not escalated:
            settled_value += bound.value_paise
        elif bound.line.line_id in resolved:
            verdict_value += bound.value_paise
        else:
            unresolved_value += bound.value_paise

    coverage_bp = bp.weighted(
        [
            (bp.FULL, settled_value),
            (VERDICT_EVIDENCE_BP, verdict_value),
            (bp.ZERO, unresolved_value),
        ]
    )

    distance = min(
        abs(alignment_bp - thresholds.approve_min_alignment_bp),
        abs(alignment_bp - thresholds.reject_max_alignment_bp),
    )
    margin_bp = bp.from_ratio(min(distance, MARGIN_WINDOW_BP), MARGIN_WINDOW_BP)

    return bp.weighted([(coverage_bp, _COVERAGE_WEIGHT), (margin_bp, _MARGIN_WEIGHT)])
