"""The merchant's truth at decision time.

A snapshot is the only thing the gate treats as authoritative about price,
stock and identity. The agent's claims are checked against it; it is never
checked against the agent.

Snapshots are hashed and the hash is recorded with every decision, so "what did
the catalog say when this was approved?" has an answer that survives the
catalog changing afterwards.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from custodian.canonical import canonical_hash
from custodian.schemas.types import Contract, Digest, Identifier, Paise, Timestamp

#: Assigned when the taxonomy lexicon has no entry for an item. Substitutions
#: involving an unknown base escalate rather than guess — see ADR-007.
UNKNOWN = "UNKNOWN"


class SanitizerFlag(StrEnum):
    """What the ingest sanitizer found in merchant-authored copy."""

    INSTRUCTION_LIKE = "INSTRUCTION_LIKE"      # imperative text aimed at an agent
    HIDDEN_TEXT = "HIDDEN_TEXT"                # zero-width chars, HTML comments
    ENCODED_PAYLOAD = "ENCODED_PAYLOAD"        # base64-ish or escaped blobs
    DIRECTION_OVERRIDE = "DIRECTION_OVERRIDE"  # RTL/LTR override characters
    PRICE_CLAIM = "PRICE_CLAIM"                # copy asserting its own price


class Sanitization(Contract):
    """The sanitizer's finding for one item.

    ``clean_text`` is what reaches the agent. ``flagged_spans`` is what was
    removed, kept as evidence — the ledger records that something was stripped,
    not merely that the feed looked fine afterwards.
    """

    flags: tuple[SanitizerFlag, ...] = ()
    flagged_spans: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.flags


class CatalogItem(Contract):
    """One normalised product.

    ``raw_name`` is preserved beside the normalised fields because normalisation
    is lossy and a dispute may need to see what the merchant actually wrote.
    """

    item_id: Identifier
    name: str = Field(min_length=1, max_length=512)
    raw_name: str = Field(min_length=1, max_length=1024)

    price_paise: Paise
    in_stock: bool

    #: Merchant copy after sanitisation. This is what reaches the agent.
    description: str = Field(default="", max_length=2_048)
    #: What the merchant actually wrote, kept as evidence. Never served to an
    #: agent — handing back the text that was stripped would defeat stripping it.
    raw_description: str = Field(default="", max_length=4_096)

    #: Attribute decomposition — the substitution primitive. See ADR-007.
    base: str = Field(default=UNKNOWN, max_length=64)
    form: str = Field(default=UNKNOWN, max_length=64)
    category: str = Field(default=UNKNOWN, max_length=64)

    #: Canonical pack size, e.g. 250 with unit "g". Both or neither.
    unit_quantity: int | None = Field(default=None, strict=True, gt=0)
    unit: str | None = Field(default=None, max_length=16)

    sanitization: Sanitization = Sanitization()

    @model_validator(mode="after")
    def _unit_pair_is_all_or_nothing(self) -> "CatalogItem":
        if (self.unit_quantity is None) != (self.unit is None):
            raise ValueError("unit_quantity and unit must be set together or not at all")
        return self

    @property
    def resolved(self) -> bool:
        """True when the taxonomy could place this item. False means escalate."""
        return self.base != UNKNOWN


class CatalogSnapshot(Contract):
    """An immutable view of one merchant's catalog at a moment in time."""

    snapshot_id: Identifier
    merchant_id: Identifier
    taken_at: Timestamp
    items: tuple[CatalogItem, ...]

    #: Versions of the hand-authored data the normalisation depended on, so a
    #: replayed decision can tell whether a later lexicon change explains a
    #: difference.
    lexicon_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _item_ids_are_unique(self) -> "CatalogSnapshot":
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate item_id in snapshot: {duplicates}")
        return self

    def digest(self) -> Digest:
        """Content hash of the catalog itself.

        ``snapshot_id`` is excluded. It is a name for the content, not part of
        it — and since the id is derived from this digest, including it would
        make the hash self-referential: naming a snapshot would change the
        digest that produced the name.
        """
        content = self.canonical()
        content.pop("snapshot_id", None)
        return canonical_hash(content)

    def find(self, item_id: str) -> CatalogItem | None:
        """Look up by id. Returns ``None`` rather than raising: an item the
        agent named and the catalog does not have is a decision input, not an
        exception."""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def __len__(self) -> int:
        return len(self.items)
