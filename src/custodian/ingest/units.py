"""Unit normalisation: ``250gm``, ``1/4 kg`` and ``pav kilo`` are one quantity.

This is a parsing problem, not a reasoning one, which is why no model is
involved (problem statement §6). Real Indian merchant exports write the same
pack size a dozen ways — digits, decimals, vulgar fractions, English words, and
transliterated Hindi quantity words that have no English equivalent in common
use. ``pav`` is a quarter, ``aadha`` is a half, ``dedh`` is one and a half,
``sawa`` is one and a quarter, ``paune`` is three quarters. A merchant writing
"pav kilo chawal" means 250g of rice, and an agent that cannot read that is
blind to a large part of the long tail.

Everything reduces to one of three canonical units — grams, millilitres, or
pieces — held as integers, for the reason everything else in this system is an
integer: a pack size that participates in a decision must have one exact
representation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Final


class Unit(StrEnum):
    """The three canonical units. Everything else converts into one of them."""

    GRAM = "g"
    MILLILITRE = "ml"
    PIECE = "piece"


@dataclass(frozen=True, slots=True)
class Measure:
    """A normalised pack size."""

    quantity: int
    unit: Unit

    def __str__(self) -> str:
        return f"{self.quantity}{self.unit}"


class UnitError(ValueError):
    """Raised when text that looked like a measure could not be normalised."""


#: Multiplier from a written unit to its canonical unit.
_UNIT_WORDS: Final[dict[str, tuple[Unit, Decimal]]] = {
    # mass
    "kg": (Unit.GRAM, Decimal(1000)), "kgs": (Unit.GRAM, Decimal(1000)),
    "kilo": (Unit.GRAM, Decimal(1000)), "kilos": (Unit.GRAM, Decimal(1000)),
    "kilogram": (Unit.GRAM, Decimal(1000)), "kilograms": (Unit.GRAM, Decimal(1000)),
    "g": (Unit.GRAM, Decimal(1)), "gm": (Unit.GRAM, Decimal(1)), "gms": (Unit.GRAM, Decimal(1)),
    "gram": (Unit.GRAM, Decimal(1)), "grams": (Unit.GRAM, Decimal(1)),
    # volume
    "l": (Unit.MILLILITRE, Decimal(1000)), "lt": (Unit.MILLILITRE, Decimal(1000)),
    "ltr": (Unit.MILLILITRE, Decimal(1000)), "ltrs": (Unit.MILLILITRE, Decimal(1000)),
    "litre": (Unit.MILLILITRE, Decimal(1000)), "litres": (Unit.MILLILITRE, Decimal(1000)),
    "liter": (Unit.MILLILITRE, Decimal(1000)), "liters": (Unit.MILLILITRE, Decimal(1000)),
    "ml": (Unit.MILLILITRE, Decimal(1)), "mls": (Unit.MILLILITRE, Decimal(1)),
    "millilitre": (Unit.MILLILITRE, Decimal(1)), "milliliter": (Unit.MILLILITRE, Decimal(1)),
    # count
    "pc": (Unit.PIECE, Decimal(1)), "pcs": (Unit.PIECE, Decimal(1)),
    "piece": (Unit.PIECE, Decimal(1)), "pieces": (Unit.PIECE, Decimal(1)),
    "no": (Unit.PIECE, Decimal(1)), "nos": (Unit.PIECE, Decimal(1)),
    "pkt": (Unit.PIECE, Decimal(1)), "pkts": (Unit.PIECE, Decimal(1)),
    "packet": (Unit.PIECE, Decimal(1)), "packets": (Unit.PIECE, Decimal(1)),
    "pack": (Unit.PIECE, Decimal(1)), "packs": (Unit.PIECE, Decimal(1)),
    "unit": (Unit.PIECE, Decimal(1)), "units": (Unit.PIECE, Decimal(1)),
    "dozen": (Unit.PIECE, Decimal(12)), "dozens": (Unit.PIECE, Decimal(12)),
}

#: Quantity words, English and transliterated Hindi. The Hindi fractions are the
#: ones a generic normaliser has no entry for.
_QUANTITY_WORDS: Final[dict[str, Decimal]] = {
    "quarter": Decimal("0.25"), "half": Decimal("0.5"), "one": Decimal(1),
    "two": Decimal(2), "three": Decimal(3), "four": Decimal(4), "five": Decimal(5),
    "six": Decimal(6), "ten": Decimal(10), "twelve": Decimal(12),
    # transliterated Hindi fractions
    "pav": Decimal("0.25"), "paav": Decimal("0.25"), "pao": Decimal("0.25"),
    "aadha": Decimal("0.5"), "adha": Decimal("0.5"), "aadhaa": Decimal("0.5"),
    "sawa": Decimal("1.25"), "savaa": Decimal("1.25"),
    "dedh": Decimal("1.5"), "derh": Decimal("1.5"), "deodh": Decimal("1.5"),
    "paune": Decimal("0.75"), "pona": Decimal("0.75"),
    "dhai": Decimal("2.5"), "dhaai": Decimal("2.5"),
    # transliterated Hindi integers
    "ek": Decimal(1), "do": Decimal(2), "teen": Decimal(3), "char": Decimal(4),
    "chaar": Decimal(4), "paanch": Decimal(5), "panch": Decimal(5),
}

#: Unicode vulgar fractions merchants paste in from elsewhere.
#:
#: These must be expanded *before* NFKC, not after. NFKC rewrites "¼" to "1⁄4"
#: using U+2044 FRACTION SLASH rather than ASCII "/", so a replacement that runs
#: afterwards never matches — and the number regex then reads the trailing "4"
#: as the whole quantity, turning "¼ kg" into 4000g. See BROKE.md 004.
_VULGAR: Final[dict[str, str]] = {"¼": "1/4", "½": "1/2", "¾": "3/4", "⅓": "1/3", "⅔": "2/3",
                                  "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}

#: U+2044 FRACTION SLASH and U+2215 DIVISION SLASH, as a second line of defence
#: for a fraction that reaches us already expanded.
_SLASHES: Final[dict[str, str]] = {"\u2044": "/", "\u2215": "/"}

_NUMBER = r"(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?|\.\d+)"
_WORDS = "|".join(sorted(_QUANTITY_WORDS, key=len, reverse=True))
_UNITS = "|".join(sorted(_UNIT_WORDS, key=len, reverse=True))

#: quantity then unit: "250 gm", "1/4 kg", "pav kilo", "1.5ltr"
_MEASURE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?P<qty>{_NUMBER}|{_WORDS})\s*(?P<unit>{_UNITS})\b", re.IGNORECASE
)


def _normalise_text(text: str) -> str:
    """Fold unicode, expand vulgar fractions, collapse whitespace."""
    expanded = text
    for glyph, expansion in _VULGAR.items():
        expanded = expanded.replace(glyph, expansion)
    folded = unicodedata.normalize("NFKC", expanded)
    for glyph, expansion in _SLASHES.items():
        folded = folded.replace(glyph, expansion)
    return re.sub(r"\s+", " ", folded).strip()


def _to_decimal(token: str) -> Decimal:
    """A quantity token as an exact Decimal. Never a float."""
    token = token.strip().lower()
    if token in _QUANTITY_WORDS:
        return _QUANTITY_WORDS[token]
    if "/" in token:
        numerator, _, denominator = token.partition("/")
        divisor = Decimal(denominator.strip())
        if divisor == 0:
            raise UnitError(f"division by zero in quantity: {token!r}")
        return Decimal(numerator.strip()) / divisor
    return Decimal(token)


def parse_measure(text: str) -> Measure:
    """Normalise a written pack size. Raises if there is none."""
    found = find_measure(text)
    if found is None:
        raise UnitError(f"no measure found in {text!r}")
    return found[0]


def find_measure(text: str) -> tuple[Measure, str] | None:
    """Extract the first measure and return it with the remaining text.

    The remainder matters: a product name with its pack size removed is what
    the taxonomy has to classify, and leaving "500ml" in the name would put a
    number where a base ingredient should be.
    """
    if not text:
        return None
    cleaned = _normalise_text(text)
    match = _MEASURE.search(cleaned)
    if match is None:
        return None

    unit_word = match.group("unit").lower()
    unit, multiplier = _UNIT_WORDS[unit_word]
    try:
        amount = _to_decimal(match.group("qty")) * multiplier
    except (ArithmeticError, ValueError) as exc:
        raise UnitError(f"unparseable quantity in {text!r}") from exc

    if amount <= 0:
        raise UnitError(f"non-positive measure in {text!r}: {amount}")

    quantity = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    remainder = (cleaned[: match.start()] + " " + cleaned[match.end() :]).strip()
    return Measure(quantity=quantity, unit=unit), re.sub(r"\s+", " ", remainder)


def same_measure(left: str, right: str) -> bool:
    """Whether two written pack sizes denote the same quantity."""
    return parse_measure(left) == parse_measure(right)
