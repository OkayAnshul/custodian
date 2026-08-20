"""What the agent proposes to buy.

Every field here is a *claim* by an untrusted client. The naming says so:
``asserted_unit_price_paise`` is what the agent says the price is, and the gate
re-derives the real one from the catalog snapshot. A field called ``price``
would invite exactly the mistake this system exists to prevent — trusting the
number the counterparty supplied.

Nothing in this module validates a claim. Validation is the gate's job, and
keeping it out of the schema means there is one place where trust is decided.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from custodian.money import line_total
from custodian.schemas.types import Contract, Identifier, Paise, Quantity


class CartLine(Contract):
    """One line the agent put in the cart."""

    line_id: Identifier
    item_id: Identifier

    #: What the agent believes it is buying. Compared against the snapshot;
    #: a mismatch means the agent's view of the catalog is stale or wrong.
    name_asserted: str = Field(min_length=1, max_length=512)

    quantity: Quantity

    #: The agent's claimed unit price. Never used to compute what is charged.
    asserted_unit_price_paise: Paise

    #: The requested-item line this is meant to satisfy, if the agent said.
    #: An unbound line is a scope-creep candidate, not an error — the agent may
    #: simply have omitted it, and the binding step re-derives it either way.
    satisfies_line_id: Identifier | None = None

    @property
    def asserted_total_paise(self) -> int:
        """The agent's arithmetic on the agent's numbers. Recomputed by the gate."""
        return line_total(self.asserted_unit_price_paise, self.quantity)


class Cart(Contract):
    """A proposed purchase, as submitted."""

    cart_id: Identifier
    merchant_id: Identifier
    lines: tuple[CartLine, ...]

    @model_validator(mode="after")
    def _line_ids_are_unique(self) -> "Cart":
        ids = [line.line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate line_id in cart")
        return self

    @model_validator(mode="after")
    def _is_not_empty(self) -> "Cart":
        if not self.lines:
            raise ValueError("an empty cart has nothing to verify")
        return self

    @property
    def asserted_total_paise(self) -> int:
        """The total the agent claims. Recorded as a claim, never charged."""
        return sum(line.asserted_total_paise for line in self.lines)
