"""Money never becomes a float. These tests exist to keep it that way."""

import pytest
from decimal import Decimal

from custodian.money import MoneyError, format_inr, line_total, parse_paise


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("₹199", 19_900),
        ("Rs. 1,299.50", 129_950),
        ("rs 45", 4_500),
        ("INR 2000", 200_000),
        ("199/-", 19_900),
        ("0.01", 1),
        ("0", 0),
        (Decimal("1299.50"), 129_950),
        (19_900, 19_900),  # ints are already paise
    ],
)
def test_parses_the_decorations_merchants_actually_export(raw, expected):
    assert parse_paise(raw) == expected


@pytest.mark.parametrize("bad", [199.5, 0.0, True, False, "abc", "", "-5", "₹", "1.2.3"])
def test_rejects_anything_it_cannot_represent_exactly(bad):
    with pytest.raises(MoneyError):
        parse_paise(bad)


def test_float_rejection_names_the_real_problem():
    with pytest.raises(MoneyError, match="ledger hash chain"):
        parse_paise(199.5)


@pytest.mark.parametrize(
    "amount,rendered",
    [
        (200_000, "₹2,000.00"),
        (1, "₹0.01"),
        (0, "₹0.00"),
        (99_900, "₹999.00"),
        (100_000, "₹1,000.00"),
        (10_000_000, "₹1,00,000.00"),        # one lakh
        (1_234_567_800, "₹1,23,45,678.00"),  # lakh/crore grouping, not 12,345,678
    ],
)
def test_formats_with_indian_digit_grouping(amount, rendered):
    assert format_inr(amount) == rendered


def test_format_refuses_floats():
    with pytest.raises(MoneyError):
        format_inr(2000.0)


def test_half_up_rounding_is_explicit():
    # Banker's rounding would give 12 here; merchants and auditors expect 13.
    assert parse_paise("0.125") == 13


def test_line_total_stays_integral():
    assert line_total(19_900, 3) == 59_700
    with pytest.raises(MoneyError):
        line_total(19_900, 2.0)
