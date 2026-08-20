"""One spelling of time, because two spellings compare wrongly."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custodian.clock import ClockError, format_utc, is_before, parse, seconds_between, utc_now


def test_now_has_no_microseconds():
    assert utc_now().endswith("+00:00")
    assert "." not in utc_now()


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-22T00:00:00Z",              # Z instead of +00:00
        "2026-08-22T00:00:00+05:30",         # not UTC
        "2026-08-22T00:00:00.123456+00:00",  # fractional seconds
        "2026-08-22T00:00:00",               # no offset
        "2026-08-22",                        # date only
        "",
        None,
    ],
)
def test_only_one_spelling_is_accepted(bad):
    with pytest.raises(ClockError):
        parse(bad)


def test_the_trap_this_module_exists_for():
    """String comparison says IST is later. As instants, it is 5.5 hours earlier."""
    ist = "2026-08-22T00:00:00+05:30"
    utc = "2026-08-22T00:00:00+00:00"
    assert ist > utc  # lexicographic — and wrong
    assert is_before(format_utc(datetime.fromisoformat(ist)), utc)  # by instant — right


def test_offsets_are_normalised_to_utc():
    ist = datetime(2026, 8, 22, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert format_utc(ist) == "2026-08-22T00:00:00+00:00"


def test_naive_datetimes_are_refused_rather_than_assumed_utc():
    with pytest.raises(ClockError, match="naive"):
        format_utc(datetime(2026, 8, 22, 0, 0))


def test_ordering_and_arithmetic():
    a, b = "2026-08-22T00:00:00+00:00", "2026-08-22T00:15:00+00:00"
    assert is_before(a, b) and not is_before(b, a) and not is_before(a, a)
    assert seconds_between(a, b) == 900
    assert seconds_between(b, a) == -900


def test_canonical_format_sorts_correctly_as_text_too():
    """Within the one accepted spelling, lexicographic order is instant order."""
    stamps = [format_utc(datetime(2026, 8, 22, tzinfo=UTC) + timedelta(seconds=s))
              for s in (0, 59, 60, 3_600, 86_400)]
    assert sorted(stamps) == stamps
