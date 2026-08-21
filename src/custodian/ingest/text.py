"""Text cleanup shared by ingest.

Merchant exports put prices inside product names, pad with marketing filler, and
mix punctuation freely. These helpers pull the structured parts out and leave
behind the text that actually identifies the product.
"""

from __future__ import annotations

import re
from typing import Final

from custodian.money import MoneyError, parse_paise

#: "₹199", "Rs. 1,299.50", "INR 2000", "199/-"
_PRICE: Final[re.Pattern[str]] = re.compile(
    r"(?:(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?)|(?:\b[\d,]+(?:\.\d+)?\s*/-)",
    re.IGNORECASE,
)

_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r"[(),\[\]{}|;:!\"'*_+@#&`~^=<>?\\]+")

#: A hyphen between two letters is a word separator, not punctuation to delete.
#: "pigeon-pea" and "pigeon pea" are the same product, and merchants write both.
#: Hyphens elsewhere (inside "1-2", at a word edge) are left alone.
_WORD_HYPHEN: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z])-(?=[a-z])", re.IGNORECASE)


def find_price(text: str) -> tuple[int, str] | None:
    """Pull a price out of free text, returning paise and the remainder.

    Returns ``None`` when there is no price rather than raising: a product name
    without an embedded price is the normal case, not an error.
    """
    match = _PRICE.search(text or "")
    if match is None:
        return None
    try:
        paise = parse_paise(match.group(0).strip())
    except MoneyError:
        return None
    remainder = (text[: match.start()] + " " + text[match.end() :]).strip()
    return paise, re.sub(r"\s+", " ", remainder)


def strip_punctuation(text: str) -> str:
    """Replace punctuation with spaces, preserving word boundaries.

    Dots are kept, because removing them would merge "1.5" into "15". Hyphens
    between letters become spaces so that a hyphenated compound matches the
    same alias its spaced spelling does.
    """
    spaced = _WORD_HYPHEN.sub(" ", text)
    return re.sub(r"\s+", " ", _PUNCTUATION.sub(" ", spaced)).strip()


def remove_phrases(text: str, phrases: frozenset[str]) -> str:
    """Drop whole-word occurrences of any phrase, longest first.

    Longest-first matters: removing "gram" before "garam masala" would leave
    "masala" behind and change what the name identifies.
    """
    result = text
    for phrase in sorted(phrases, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(phrase)}\b", " ", result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip()
