"""Money is integer paise. There is no float path through this module.

Every amount that can affect a payment decision is an ``int`` count of paise.
Floats are rejected at the boundary rather than tolerated and rounded, because
a float that reaches the ledger has no canonical serialisation and therefore
breaks replay (see ``custodian.canonical``).

    >>> parse_paise("Rs. 1,299.50")
    129950
    >>> format_inr(200000)
    '₹2,000.00'
    >>> format_inr(1234567800)
    '₹1,23,45,678.00'
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Final

PAISE_PER_RUPEE: Final[int] = 100

#: Currency decoration seen in real Indian merchant exports: "₹199", "Rs. 199",
#: "INR 199", "199/-". Stripped before the amount is parsed.
_DECORATION: Final[re.Pattern[str]] = re.compile(
    r"""^\s*(?:₹|rs\.?|inr)?\s*   # leading symbol
        (?P<amount>[0-9,]+(?:\.[0-9]+)?)
        \s*(?:/-)?\s*$            # trailing "/-"
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TWO_PLACES: Final[Decimal] = Decimal("0.01")


class MoneyError(ValueError):
    """Raised when a value cannot be represented exactly as integer paise."""


def _reject_float(value: object) -> None:
    """Refuse floats explicitly, so the failure names the real problem.

    ``bool`` is a subclass of ``int`` but is never a valid amount either.
    """
    if isinstance(value, float):
        raise MoneyError(
            f"float is not a valid money input: {value!r}. "
            "Pass a str, int (paise), or Decimal — floats cannot round-trip "
            "through the ledger hash chain."
        )
    if isinstance(value, bool):
        raise MoneyError(f"bool is not a valid money input: {value!r}")


def parse_paise(raw: str | int | Decimal) -> int:
    """Parse a rupee amount into integer paise.

    Accepts the decorated forms merchants actually export. An ``int`` is taken
    to already be paise; a ``str`` or ``Decimal`` is taken to be rupees.
    """
    _reject_float(raw)

    if isinstance(raw, int):
        if raw < 0:
            raise MoneyError(f"negative amount: {raw}")
        return raw

    if isinstance(raw, Decimal):
        rupees = raw
    else:
        match = _DECORATION.match(raw)
        if match is None:
            raise MoneyError(f"unparseable amount: {raw!r}")
        try:
            rupees = Decimal(match.group("amount").replace(",", ""))
        except InvalidOperation as exc:  # pragma: no cover - guarded by regex
            raise MoneyError(f"unparseable amount: {raw!r}") from exc

    if rupees < 0:
        raise MoneyError(f"negative amount: {raw!r}")

    quantised = rupees.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return int(quantised * PAISE_PER_RUPEE)


def _group_indian(whole: int) -> str:
    """Lakh/crore digit grouping: 12345678 -> ``'1,23,45,678'``.

    Western grouping would render ₹1,23,45,678 as ₹12,345,678, which an Indian
    merchant reads wrong at a glance. The value is unchanged either way; this is
    presentation, and presentation is where a demo loses credibility.
    """
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        head, group = head[:-2], head[-2:]
        groups.insert(0, group)
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def format_inr(amount_paise: int) -> str:
    """Render paise for humans: ``200000`` -> ``'₹2,000.00'``.

    Presentation only. Never parse the output of this function back.
    """
    _reject_float(amount_paise)
    if not isinstance(amount_paise, int):
        raise MoneyError(f"expected int paise, got {type(amount_paise).__name__}")

    sign = "-" if amount_paise < 0 else ""
    whole, part = divmod(abs(amount_paise), PAISE_PER_RUPEE)
    return f"{sign}₹{_group_indian(whole)}.{part:02d}"


def line_total(unit_price_paise: int, quantity: int) -> int:
    """Total for one cart line. Integer multiplication, no rounding step."""
    _reject_float(unit_price_paise)
    _reject_float(quantity)
    if quantity < 0:
        raise MoneyError(f"negative quantity: {quantity}")
    return unit_price_paise * quantity
