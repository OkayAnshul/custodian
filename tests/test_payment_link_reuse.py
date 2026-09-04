"""Minting a payable link twice for the same receipt.

Razorpay's ``reference_id`` reads like an idempotency key and is not one: it is
a uniqueness constraint, so a second creation under the same reference is
refused outright rather than returning the first link. The demo mints under a
fixed receipt, so every run after the first hit that refusal and printed "link
unavailable" — the first thing a live run showed a viewer.

Falling through to the existing link is only safe if two things are proved
first, and those are what most of this file is about: the link must be for the
amount this order re-derived, and it must still be payable. A URL that charges
a different amount, or one for an order already paid, is worse than the error.
"""

import pytest

from custodian.payments.gateway import OrderRef, PaymentError
from custodian.payments.razorpay_client import RazorpayGateway

ORDER = OrderRef(order_id="order_TEST123", amount_paise=69_800, currency="INR",
                 receipt="demo-1", payment_url=None)


class _Duplicate(Exception):
    """Shaped like the provider's own complaint, which is a plain 400."""

    def __str__(self) -> str:
        return ("payment link with given reference_id: demo-1-link already exists. "
                "Please create a payment link with a different reference_id")


class _QuotaReached(Exception):
    """The other refusal that leaves a perfectly good link sitting there.

    Razorpay caps test-mode payment links at 30 per account, for the lifetime
    of the account — cancelling one does not free a slot. The message shares
    no words with the duplicate-reference error, which is exactly why keying
    reuse on the message text was wrong.
    """

    def __str__(self) -> str:
        return "test mode limit of 30 reached for payment_link"


class _Links:
    def __init__(self, existing: list[dict], *, refuse: bool = True):
        self.existing = existing
        self.refuse = refuse
        self.created: list[dict] = []
        self.listed: list[dict] = []

    def create(self, payload: dict) -> dict:
        if self.refuse:
            raise _Duplicate()
        self.created.append(payload)
        return {"short_url": "https://rzp.io/rzp/FRESH01"}

    def all(self, query: dict) -> dict:
        self.listed.append(query)
        return {"payment_links": self.existing}


class _Client:
    def __init__(self, links: _Links):
        self.payment_link = links


def gateway_for(links: _Links) -> RazorpayGateway:
    return RazorpayGateway(client=_Client(links))


def test_a_first_mint_creates_a_link_under_the_receipts_reference():
    links = _Links([], refuse=False)
    assert gateway_for(links).payment_link_for(ORDER) == "https://rzp.io/rzp/FRESH01"
    assert links.created[0]["reference_id"] == "demo-1-link"
    assert links.created[0]["amount"] == 69_800


def test_minting_twice_returns_the_link_that_already_exists():
    links = _Links([{"id": "plink_1", "status": "created", "amount": 69_800,
                     "short_url": "https://rzp.io/rzp/EXIST01"}])
    assert gateway_for(links).payment_link_for(ORDER) == "https://rzp.io/rzp/EXIST01"
    assert links.listed == [{"reference_id": "demo-1-link"}]


def test_a_quota_refusal_still_finds_the_link_that_already_exists():
    """The real case, and the one the first fix missed.

    The provider refused for a reason that has nothing to do with references,
    and a usable link for this order was sitting there the whole time.
    """
    class _Capped(_Links):
        def create(self, payload):
            raise _QuotaReached()

    links = _Capped([{"id": "plink_1", "status": "created", "amount": 69_800,
                      "short_url": "https://rzp.io/rzp/EXIST01"}])
    assert gateway_for(links).payment_link_for(ORDER) == "https://rzp.io/rzp/EXIST01"


def test_a_link_for_a_different_amount_is_never_handed_back():
    """The amount is the one control this system is built around.

    A link minted under the same receipt for a different total is not this
    order's link, however convenient returning it would be — so the provider's
    own refusal is re-raised rather than the wrong URL returned.
    """
    links = _Links([{"id": "plink_1", "status": "created", "amount": 145_000,
                     "short_url": "https://rzp.io/rzp/WRONG01"}])
    with pytest.raises(PaymentError, match="already exists"):
        gateway_for(links).payment_link_for(ORDER)


@pytest.mark.parametrize("status", ["paid", "cancelled", "expired"])
def test_a_link_that_can_no_longer_take_money_is_not_reused(status):
    """A paid link keeps its URL. Handing it back invites a second payment."""
    links = _Links([{"id": "plink_1", "status": status, "amount": 69_800,
                     "short_url": "https://rzp.io/rzp/DONE01"}])
    with pytest.raises(PaymentError, match="already exists"):
        gateway_for(links).payment_link_for(ORDER)


def test_a_failure_with_nothing_to_reuse_surfaces_the_providers_own_error():
    """When the lookup finds nothing usable, the operator sees why creation failed.

    That is more actionable than a message about reuse, because the reason the
    provider refused is the thing that has to be fixed.
    """
    class _Refuses(_Links):
        def create(self, payload):
            raise ValueError("amount must be at least INR 1.00")

    with pytest.raises(PaymentError, match="amount must be at least"):
        gateway_for(_Refuses([])).payment_link_for(ORDER)


def test_the_amount_check_survives_a_provider_returning_junk():
    """A listing entry without a usable amount is skipped, not trusted."""
    links = _Links([{"id": "plink_1", "status": "created", "amount": None,
                     "short_url": "https://rzp.io/rzp/JUNK01"},
                    {"id": "plink_2", "status": "created", "amount": 69_800,
                     "short_url": "https://rzp.io/rzp/GOOD01"}])
    assert gateway_for(links).payment_link_for(ORDER) == "https://rzp.io/rzp/GOOD01"
