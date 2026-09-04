"""Settlement the provider performed itself.

A Razorpay account can be set to capture automatically: the payment is captured
the moment the payer completes on the hosted page, so Custodian's own capture
call arrives second and is refused with `AlreadyCaptured`. Before this was
handled, that refusal produced a 409 and *no ledger entry at all* — the trail
ended at PAYMENT_INITIATED for a payment that had actually settled.

That is the one failure this ledger may not have. Everything the project claims
rests on a dispute being resolvable from the record, and money moving without a
record is worse than money not moving.

The fake gateway never auto-captures, which is why no test caught it and why it
took paying on the real page to find. See `BROKE.md` 016.
"""

from dataclasses import dataclass

import pytest

from custodian.gate.service import AmountMismatch, Custodian
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent.parser import resolve
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.store import ArtifactStore
from custodian.payments.fake import FakeGateway
from custodian.payments.gateway import AlreadyCaptured, PaymentRef, PaymentStatus
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.mandate import Mandate

NOW = "2026-08-21T12:00:00+00:00"


@dataclass
class Rig:
    custodian: Custodian
    request_id: str


@pytest.fixture
def approved():
    """One clean, approved decision — the state a payer starts from."""
    snapshot, _ = ingest_csv("data/catalog/kirana_export.csv", merchant_id="m1", taken_at=NOW)
    custodian = Custodian(ledger=Ledger.in_memory(), store=ArtifactStore.in_memory(),
                          tables=SubstitutionTables.from_taxonomy(default_taxonomy()))
    intent = resolve({"goal": "ingredients for a thai curry, under Rs 2000",
                      "budget_paise": 300_000, "merchant_scope": ["m1"],
                      "substitution_policy": "SAME_BASE",
                      "requested_items": [{"raw_text": "coconut milk", "quantity": 2},
                                          {"raw_text": "thai red curry paste", "quantity": 1}]},
                     intent_id="i1")

    def line(lid, sku, qty, satisfies):
        item = snapshot.find(sku)
        return CartLine(line_id=lid, item_id=sku, name_asserted=item.name, quantity=qty,
                        asserted_unit_price_paise=item.price_paise, satisfies_line_id=satisfies)

    mandate = Mandate(mandate_id="mnd", max_amount_paise=1_000_000,
                      per_transaction_cap_paise=300_000,
                      valid_from="2026-08-01T00:00:00+00:00",
                      valid_until="2026-09-30T00:00:00+00:00", merchant_allowlist=("m1",))
    custodian.evaluate(
        request_id="req-1", intent=intent,
        cart=Cart(cart_id="c1", merchant_id="m1",
                  lines=(line("l1", "SKU001", 2, "i1-r1"), line("l2", "SKU055", 1, "i1-r2"))),
        snapshot=snapshot, mandate=mandate, thresholds=DEFAULT, evaluated_at=NOW)
    return Rig(custodian=custodian, request_id="req-1")


class AutoCapturingGateway(FakeGateway):
    """A provider that settles on its own, the way an auto-capture account does."""

    def __init__(self, *, settled_amount_paise: int | None = None):
        super().__init__()
        self._settled_amount = settled_amount_paise

    def capture(self, payment, *, idempotency_key):
        raise AlreadyCaptured(f"payment {payment.payment_id} has already been captured")

    def fetch(self, payment_id: str) -> PaymentRef:
        ref = super().fetch(payment_id)
        return PaymentRef(
            payment_id=ref.payment_id, order_id=ref.order_id,
            amount_paise=self._settled_amount or ref.amount_paise,
            status=PaymentStatus.CAPTURED,
        )


def settle(rig, gateway):
    """Take an approved decision all the way to a capture attempt."""
    order = rig.custodian.open_order(rig.request_id, gateway)
    gateway.simulate_payer(order)
    return rig.custodian.capture(rig.request_id, gateway, order)


def test_a_payment_the_provider_captured_is_still_recorded(approved):
    """The trail must account for money that moved, whoever moved it."""
    gateway = AutoCapturingGateway()
    payment = settle(approved, gateway)

    assert payment.settled
    events = approved.custodian.ledger.read(approved.request_id)
    settled = [e for e in events if e.event_type is EventType.PAYMENT_SETTLED]
    assert len(settled) == 1, "a settled payment with no settlement event is the failure"
    assert settled[0].inferred["captured_by"] == gateway.name


def test_the_record_says_who_captured_it(approved):
    """Custodian capturing and the provider capturing are different facts."""
    ours = settle(approved, FakeGateway())
    assert ours.settled
    events = approved.custodian.ledger.read(approved.request_id)
    settled = [e for e in events if e.event_type is EventType.PAYMENT_SETTLED]
    assert settled[0].inferred["captured_by"] == "custodian"


def test_a_second_capture_is_still_refused(approved):
    """The protection this exception exists for must survive the new path.

    The ledger decides, not the provider: the question is whether *we* have
    accounted for this payment, and only the record can answer it.
    """
    gateway = AutoCapturingGateway()
    settle(approved, gateway)
    order = approved.custodian.open_order(approved.request_id, gateway)
    with pytest.raises(AlreadyCaptured):
        approved.custodian.capture(approved.request_id, gateway, order)


def test_an_auto_captured_wrong_amount_is_refused_and_recorded(approved):
    """The amount check must not be skipped by the path that bypasses capture.

    On this path the settled amount is seen for the first time *after* the
    provider took it, so it is checked against the approved amount there too.
    """
    gateway = AutoCapturingGateway(settled_amount_paise=999_99)
    order = approved.custodian.open_order(approved.request_id, gateway)
    gateway.simulate_payer(order)
    with pytest.raises(AmountMismatch):
        approved.custodian.capture(approved.request_id, gateway, order)

    events = approved.custodian.ledger.read(approved.request_id)
    failed = [e for e in events if e.event_type is EventType.PAYMENT_FAILED]
    assert failed and failed[-1].inferred["refused"] == "AMOUNT_MISMATCH"
    assert not [e for e in events if e.event_type is EventType.PAYMENT_SETTLED]
