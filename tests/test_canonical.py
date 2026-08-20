"""Canonical bytes are the precondition for replay."""

import pytest
from decimal import Decimal

from custodian.canonical import (
    CanonicalisationError,
    canonical_bytes,
    canonical_hash,
    canonical_json,
    is_hash,
)


def test_key_order_does_not_change_the_hash():
    a = {"b": 1, "a": {"z": [1, 2], "y": "₹2,000.00"}}
    b = {"a": {"y": "₹2,000.00", "z": [1, 2]}, "b": 1}
    assert canonical_hash(a) == canonical_hash(b)


def test_output_has_no_insignificant_whitespace():
    assert canonical_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'


def test_unicode_is_preserved_as_utf8_not_escaped():
    assert canonical_bytes({"p": "₹"}) == '{"p":"₹"}'.encode("utf-8")


@pytest.mark.parametrize(
    "bad",
    [
        {"score": 0.85},
        {"nested": [1, {"deep": 2.0}]},
        [1.5],
        {"d": Decimal("1.5")},
        {1: "int key"},
        {"s": {1, 2}},
        {"b": b"bytes"},
    ],
)
def test_rejects_values_with_no_stable_byte_form(bad):
    with pytest.raises(CanonicalisationError):
        canonical_bytes(bad)


def test_float_rejection_points_at_the_offending_path():
    with pytest.raises(CanonicalisationError, match=r"\$\.nested\[1\]\.deep"):
        canonical_bytes({"nested": [1, {"deep": 2.0}]})


def test_bools_and_null_survive_because_json_encodes_them_exactly():
    assert canonical_json({"t": True, "f": False, "n": None}) == '{"f":false,"n":null,"t":true}'


def test_is_hash_recognises_its_own_output():
    assert is_hash(canonical_hash({"a": 1}))
    assert not is_hash("not-a-hash")
    assert not is_hash("A" * 64)  # uppercase is not what we emit
