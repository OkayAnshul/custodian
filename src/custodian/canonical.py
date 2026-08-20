"""Deterministic serialisation and hashing for the evidence ledger.

Replay is only meaningful if the same logical value always produces the same
bytes. This module is the single place that guarantees it.

Three rules, each of which exists because breaking it silently breaks replay:

1. **Keys are sorted, whitespace is insignificant.** Python dict order is
   insertion order; two structurally identical payloads built by different code
   paths would otherwise hash differently.
2. **Floats are rejected outright.** ``0.1 + 0.2`` has no stable decimal form,
   and repr differs across platforms. Money is integer paise
   (``custodian.money``); scores are integer basis points (``custodian.bp``).
3. **Composite hashes hash a structure, never a concatenation.** Concatenating
   ``event_type + event_id`` is ambiguous — ``"AB" + "C"`` and ``"A" + "BC"``
   collide. Hashing a canonical object is unambiguous by construction.

This is RFC 8785 (JCS) in spirit. It differs in one respect worth stating
rather than glossing: JCS sorts keys by UTF-16 code unit, while Python sorts by
code point. The two agree for every key in this system (all ASCII), but the
implementation is not a general-purpose JCS encoder and is not claimed to be.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Final

#: The ``prev_hash`` of the first event in a chain.
GENESIS_HASH: Final[str] = "0" * 64

_HEX_LEN: Final[int] = 64


class CanonicalisationError(TypeError):
    """Raised when a value has no deterministic serialisation."""


def _validate(node: Any, path: str = "$") -> None:
    """Reject anything without a stable byte representation, naming the path."""
    if isinstance(node, bool) or node is None or isinstance(node, (str, int)):
        return  # bool/int/str/null all encode deterministically

    if isinstance(node, float):
        raise CanonicalisationError(
            f"float at {path}: {node!r}. Floats have no canonical form and must "
            "never enter the hash chain — use integer paise (custodian.money) "
            "or integer basis points (custodian.bp)."
        )
    if isinstance(node, Decimal):
        raise CanonicalisationError(
            f"Decimal at {path}: {node!r}. Convert explicitly at the boundary "
            "so the rounding decision is visible in the code, not implicit here."
        )
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise CanonicalisationError(
                    f"non-string key at {path}: {key!r} ({type(key).__name__}). "
                    "JSON would coerce it silently; that coercion is not reversible."
                )
            _validate(value, f"{path}.{key}")
        return
    if isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _validate(value, f"{path}[{index}]")
        return

    raise CanonicalisationError(
        f"unserialisable type at {path}: {type(node).__name__}"
    )


def canonical_bytes(value: Any) -> bytes:
    """Serialise ``value`` to its one canonical UTF-8 byte representation."""
    _validate(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    """Canonical form as ``str``, for storage in a SQLite TEXT column."""
    return canonical_bytes(value).decode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    """Hash a structure by way of its canonical bytes."""
    return sha256_hex(canonical_bytes(value))


def is_hash(value: object) -> bool:
    """True if ``value`` looks like a hash this module produced."""
    return (
        isinstance(value, str)
        and len(value) == _HEX_LEN
        and all(c in "0123456789abcdef" for c in value)
    )
