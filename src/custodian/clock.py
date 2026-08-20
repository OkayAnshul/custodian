"""Time, in exactly one format.

Timestamps in this system are compared — is this mandate still live, is this
snapshot stale — and they are hashed into the ledger. Both uses demand a single
representation.

ISO-8601 permits several spellings of the same instant: ``Z`` and ``+00:00``,
``+05:30``, optional fractional seconds at any precision. That is fatal twice
over. Hashing is broken because the same instant produces different bytes.
Comparison is broken worse, and silently:

    '2026-08-22T00:00:00+05:30' > '2026-08-22T00:00:00+00:00'   # as strings
    …but it is 5.5 hours *earlier* in absolute time.

A mandate-expiry check written on string comparison would pass an expired
mandate. So this module defines one spelling — UTC, second precision,
``+00:00`` — enforced at the schema boundary, and compares by parsing rather
than by string order, so a format slip cannot silently produce a wrong answer.

Nothing here is called from inside a decision. ``decide()`` receives the moment
to evaluate at as an input (ADR-010); a function that reads a clock cannot be
replayed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

#: The one accepted spelling: ``2026-08-21T03:45:12+00:00``.
ISO_UTC_SECONDS: Final[re.Pattern[str]] = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$"
)


class ClockError(ValueError):
    """Raised when a timestamp is not in the one accepted format."""


def utc_now() -> str:
    """Current time in the canonical format. Never called inside a decision."""
    return format_utc(datetime.now(UTC))


def format_utc(moment: datetime) -> str:
    """Render any aware datetime in the canonical format.

    Naive datetimes are refused rather than assumed to be UTC — assuming is how
    a five-and-a-half-hour error gets in.
    """
    if moment.tzinfo is None:
        raise ClockError(f"naive datetime has no defined instant: {moment!r}")
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


def parse(timestamp: str) -> datetime:
    """Parse a canonical timestamp. Rejects any other spelling."""
    if not isinstance(timestamp, str) or not ISO_UTC_SECONDS.match(timestamp):
        raise ClockError(
            f"timestamp must be UTC with second precision, e.g. "
            f"'2026-08-21T03:45:12+00:00' — got {timestamp!r}"
        )
    return datetime.fromisoformat(timestamp)


def is_before(earlier: str, later: str) -> bool:
    """``earlier < later``, compared as instants rather than as text."""
    return parse(earlier) < parse(later)


def seconds_between(earlier: str, later: str) -> int:
    """Whole seconds from ``earlier`` to ``later``. Negative if reversed."""
    return int((parse(later) - parse(earlier)).total_seconds())
