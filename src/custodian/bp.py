"""Scores are integer basis points: 0 = 0.00, 10000 = 100.00%.

Every score that reaches a decision or the ledger is an ``int``, for the same
reason money is (see ``custodian.canonical``): floats have no canonical byte
form, so a float score makes a decision unreplayable. Basis points give four
significant digits, which is more resolution than any threshold in this system
needs, and all arithmetic below stays in the integers.
"""

from __future__ import annotations

from typing import Final, Iterable

FULL: Final[int] = 10_000
ZERO: Final[int] = 0


class BpError(ValueError):
    """Raised when a value is not a valid basis-point score."""


def validate(score: int) -> int:
    """Return ``score`` if it is a valid basis-point value, else raise."""
    if isinstance(score, bool) or not isinstance(score, int):
        raise BpError(f"basis points must be int, got {type(score).__name__}: {score!r}")
    if not ZERO <= score <= FULL:
        raise BpError(f"basis points out of range [0, {FULL}]: {score}")
    return score


def from_ratio(numerator: int, denominator: int) -> int:
    """Convert a ratio to basis points, rounding half up, in integer arithmetic.

    ``from_ratio(1, 3)`` -> ``3333``. A zero denominator is a caller bug rather
    than a score of zero, so it raises.
    """
    if isinstance(numerator, float) or isinstance(denominator, float):
        raise BpError("from_ratio takes ints; floats cannot enter a score")
    if denominator == 0:
        raise BpError("from_ratio: zero denominator — the caller must decide what empty means")
    if numerator < 0 or denominator < 0:
        raise BpError(f"from_ratio: negative input {numerator}/{denominator}")
    return validate(min(FULL, (numerator * FULL + denominator // 2) // denominator))


def from_percent(percent: str) -> int:
    """Parse a human-written percentage such as ``"85"`` or ``"85.5"``."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

    try:
        value = Decimal(percent)
    except InvalidOperation as exc:
        raise BpError(f"unparseable percentage: {percent!r}") from exc
    scaled = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return validate(int(scaled))


def weighted(parts: Iterable[tuple[int, int]]) -> int:
    """Weighted mean of ``(score_bp, weight)`` pairs, in integer arithmetic.

    Weights are arbitrary positive ints; only their ratios matter. Returns
    ``ZERO`` for an empty iterable — an unweighted aggregate has no evidence
    behind it, and a caller that means "no opinion" should not be aggregating.
    """
    pairs = [(validate(score), weight) for score, weight in parts]
    if any(w < 0 for _, w in pairs):
        raise BpError("negative weight")
    total_weight = sum(w for _, w in pairs)
    if total_weight == 0:
        return ZERO
    numerator = sum(score * weight for score, weight in pairs)
    return validate((numerator + total_weight // 2) // total_weight)


def to_str(score: int) -> str:
    """Render basis points for humans: ``8500`` -> ``'85.00%'``."""
    validate(score)
    whole, part = divmod(score, 100)
    return f"{whole}.{part:02d}%"
