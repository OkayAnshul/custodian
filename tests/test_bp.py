"""Scores stay integral, for the same reason money does."""

import pytest

from custodian import bp


@pytest.mark.parametrize(
    "num,den,expected",
    [(1, 3, 3_333), (2, 3, 6_667), (1, 1, 10_000), (0, 5, 0), (1, 2, 5_000), (1, 8, 1_250)],
)
def test_ratios_round_half_up_in_integer_arithmetic(num, den, expected):
    assert bp.from_ratio(num, den) == expected


def test_a_ratio_above_one_clamps_rather_than_overflowing_the_scale():
    assert bp.from_ratio(3, 2) == bp.FULL


def test_zero_denominator_is_a_caller_bug_not_a_zero_score():
    with pytest.raises(bp.BpError, match="empty"):
        bp.from_ratio(1, 0)


@pytest.mark.parametrize("bad", [0.85, True, "8500", None, -1, 10_001])
def test_rejects_anything_that_is_not_a_valid_score(bad):
    with pytest.raises(bp.BpError):
        bp.validate(bad)


def test_floats_cannot_enter_through_a_ratio():
    with pytest.raises(bp.BpError):
        bp.from_ratio(1.0, 3)


@pytest.mark.parametrize("text,expected", [("85", 8_500), ("85.5", 8_550), ("0", 0), ("100", 10_000)])
def test_parses_human_written_percentages(text, expected):
    assert bp.from_percent(text) == expected


def test_weighted_mean_is_integral():
    assert bp.weighted([(10_000, 3), (0, 1)]) == 7_500
    assert bp.weighted([(9_000, 1), (8_000, 1)]) == 8_500


def test_weighted_mean_of_nothing_is_zero_not_an_error():
    """No evidence aggregates to no score; the caller decides what that means."""
    assert bp.weighted([]) == bp.ZERO
    assert bp.weighted([(9_000, 0)]) == bp.ZERO


def test_weighted_mean_stays_in_range():
    assert 0 <= bp.weighted([(10_000, 7), (1, 1)]) <= bp.FULL


@pytest.mark.parametrize("score,text", [(8_500, "85.00%"), (3_333, "33.33%"), (10_000, "100.00%"), (0, "0.00%")])
def test_renders_for_humans(score, text):
    assert bp.to_str(score) == text
