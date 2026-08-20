"""The payment authority envelope.

This models the guarantee AP2 provides, and NPCI's UAP provides in India: a
human authorised this agent to spend, within these limits, for this window.

**Modelled, not integrated.** Custodian does not call UPI Reserve Pay or an AP2
issuer; those are not reachable from a self-serve test account. The mandate is
constructed locally and checked deterministically, and the README says so
plainly rather than implying an integration that does not exist. What the
project demonstrates is the layer *above* the mandate — the mandate is an input
it consumes, exactly as the problem statement's §8 argues it should be.

The mandate answers "was this permitted?". Everything else in the gate answers
"was this what was asked for?". Keeping them in separate objects keeps the two
questions from being confused for one another.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from custodian.clock import is_before
from custodian.schemas.types import Contract, Identifier, Paise, Timestamp


class Mandate(Contract):
    """What the human authorised, independent of what they asked for."""

    mandate_id: Identifier

    #: Ceiling across the mandate's lifetime.
    max_amount_paise: Paise
    #: Ceiling for any single transaction. Never above ``max_amount_paise``.
    per_transaction_cap_paise: Paise

    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")

    valid_from: Timestamp
    valid_until: Timestamp

    #: Merchants this mandate may pay. Empty means none — a mandate that
    #: authorises payment to anyone is not a mandate.
    merchant_allowlist: tuple[Identifier, ...]

    #: Categories this mandate covers. ``None`` means uncategorised spending is
    #: permitted; an empty tuple means nothing is.
    category_allowlist: tuple[str, ...] | None = None

    revoked: bool = False

    @model_validator(mode="after")
    def _per_transaction_cap_fits_inside_the_envelope(self) -> "Mandate":
        if self.per_transaction_cap_paise > self.max_amount_paise:
            raise ValueError(
                f"per_transaction_cap_paise ({self.per_transaction_cap_paise}) exceeds "
                f"max_amount_paise ({self.max_amount_paise})"
            )
        return self

    @model_validator(mode="after")
    def _window_is_ordered(self) -> "Mandate":
        if not is_before(self.valid_from, self.valid_until):
            raise ValueError(f"mandate window ends before it starts: {self.valid_from} .. {self.valid_until}")
        return self

    @model_validator(mode="after")
    def _authorises_at_least_one_merchant(self) -> "Mandate":
        if not self.merchant_allowlist:
            raise ValueError("a mandate with an empty merchant allowlist authorises nothing")
        return self

    def covers_merchant(self, merchant_id: str) -> bool:
        return merchant_id in self.merchant_allowlist

    def covers_category(self, category: str) -> bool:
        return self.category_allowlist is None or category in self.category_allowlist

    def active_at(self, moment: str) -> bool:
        """Whether the mandate is live at ``moment``.

        Takes the time as an argument. Reading a clock here would make every
        decision that depends on it unreplayable (ADR-010). Compared as
        instants rather than as strings — see ``custodian.clock``.
        """
        if self.revoked:
            return False
        return not is_before(moment, self.valid_from) and is_before(moment, self.valid_until)
