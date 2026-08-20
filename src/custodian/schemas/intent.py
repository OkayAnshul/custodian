"""What the human asked for, made explicit.

The free-text goal is carried as a field and never as the authority. Everything
the gate acts on — budget, merchant scope, substitution policy, the items
themselves — is a structured constraint that deterministic code can check.
That separation is the whole point: a prompt is not a security boundary, so the
prompt is not what the gate reads.

An LLM produces this structure from natural language (model position #1 of two).
It does not get to decide anything afterwards.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from custodian.schemas.catalog import UNKNOWN
from custodian.schemas.types import Contract, Identifier, Paise, Quantity


class SubstitutionPolicy(StrEnum):
    """How much latitude the human gave the agent.

    This is the human's instruction, not the gate's threshold. A substitution
    can be judged perfectly faithful and still be refused because the human
    said ``EXACT_ONLY``.
    """

    EXACT_ONLY = "EXACT_ONLY"    # no substitutions at all
    SAME_BASE = "SAME_BASE"      # coconut milk -> coconut cream, never almond milk
    EQUIVALENT = "EQUIVALENT"    # any substitution that preserves intent


class RequestedItem(Contract):
    """One thing the human asked for.

    ``base``/``form``/``category`` are filled by the same taxonomy that
    normalises the catalog, so a request and a catalog item are compared in one
    vocabulary rather than by string similarity (ADR-007). ``UNKNOWN`` means the
    taxonomy could not place it, which routes to escalation rather than a guess.
    """

    line_id: Identifier
    raw_text: str = Field(min_length=1, max_length=512)
    quantity: Quantity = 1

    base: str = Field(default=UNKNOWN, max_length=64)
    form: str = Field(default=UNKNOWN, max_length=64)
    category: str = Field(default=UNKNOWN, max_length=64)

    #: Per-item ceiling, if the human named one ("milk, nothing over ₹80").
    max_unit_price_paise: Paise | None = None

    @property
    def resolved(self) -> bool:
        return self.base != UNKNOWN


class Intent(Contract):
    """The structured mandate for one shopping request."""

    intent_id: Identifier

    #: The human's words, preserved for the record and for the ledger. Read by
    #: humans and by the intent parser; never by the gate.
    goal: str = Field(min_length=1, max_length=2_048)

    #: Total the human authorised for this request. ``None`` defers entirely to
    #: the payment mandate's caps.
    budget_paise: Paise | None = None

    #: Merchants the human named. Empty means the human named none, which is
    #: not the same as "any merchant is fine" — the gate resolves that against
    #: the mandate's allowlist rather than assuming.
    merchant_scope: tuple[Identifier, ...] = ()

    #: Categories in scope. ``None`` means the human did not restrict category.
    category_scope: tuple[str, ...] | None = None

    requested_items: tuple[RequestedItem, ...]
    substitution_policy: SubstitutionPolicy = SubstitutionPolicy.SAME_BASE

    @model_validator(mode="after")
    def _line_ids_are_unique(self) -> "Intent":
        ids = [item.line_id for item in self.requested_items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate line_id in requested_items")
        return self

    @model_validator(mode="after")
    def _asks_for_something(self) -> "Intent":
        if not self.requested_items:
            raise ValueError("an intent with no requested items cannot be satisfied or violated")
        return self

    def find(self, line_id: str) -> RequestedItem | None:
        for item in self.requested_items:
            if item.line_id == line_id:
                return item
        return None
