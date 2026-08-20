"""Shared field types and the base every data contract inherits.

Three defaults are set here rather than repeated on each model, because each
one is a control and a control that has to be remembered is not a control.

**Strict numerics.** Pydantic's default is to coerce ``199.0`` to ``199``
silently. That would walk a float straight past the integer-paise guarantee
(ADR-001) and land it in a ledger payload, where it has no canonical form.
``Paise`` and ``ScoreBp`` are strict, so the coercion raises instead.

**``extra="forbid"``.** The buying agent is an untrusted client. Ignoring
unknown fields means an agent can attach anything it likes to a request and
have it silently dropped; forbidding them means the request is rejected and the
attempt is visible.

**``frozen=True``.** These objects are evidence. A model that can be mutated
after it was hashed is a model whose hash means nothing.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

#: An amount of money, in paise. Never rupees, never a float. See ADR-001.
Paise = Annotated[int, Field(strict=True, ge=0)]

#: A score in basis points, 0–10000. See ADR-002.
ScoreBp = Annotated[int, Field(strict=True, ge=0, le=10_000)]

#: A count of units. Zero is not a cart line.
Quantity = Annotated[int, Field(strict=True, gt=0)]

#: A non-empty identifier.
Identifier = Annotated[str, Field(min_length=1, max_length=128)]

#: An ISO-8601 timestamp: UTC, second precision, ``+00:00``. One spelling only.
#:
#: Deliberately not ``datetime``. Timestamps here are *recorded*, *compared* and
#: *hashed*, never read from a clock inside a decision (ADR-010). The pattern is
#: narrow on purpose — ISO-8601 admits ``Z``, ``+05:30`` and optional fractional
#: seconds, which breaks hashing (one instant, several byte sequences) and
#: breaks comparison silently. See ``custodian.clock``.
Timestamp = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")]

#: A SHA-256 hex digest as produced by ``custodian.canonical``.
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Contract(BaseModel):
    """Base for every data contract that crosses a trust boundary."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        str_strip_whitespace=True,
    )

    def canonical(self) -> dict[str, Any]:
        """A JSON-safe dict suitable for hashing and for the ledger.

        ``custodian.canonical`` re-validates on the way in, so a float that
        somehow reached a field still cannot reach the chain.
        """
        return self.model_dump(mode="json")
