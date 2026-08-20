"""Ledger and payments together: the spine the Day 5 checkpoint runs on.

Unit tests prove each piece in isolation. This proves the sequence — that a
settlement produces evidence, that evidence verifies, and that the failure and
retry paths write the truth rather than the intent.
"""

import pytest

from custodian.canonical import GENESIS_HASH
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.verify import verify_chain
from custodian.money import parse_paise
from custodian.payments.fake import FakeGateway
from custodian.payments.gateway import AlreadyCaptured, PaymentStatus


@pytest.fixture
def rig(tmp_path):
    return Ledger.open(tmp_path / "ledger.db"), FakeGateway()


def settle(ledger: Ledger, gateway, request_id: str, amount_paise: int):
    """Create, capture, and record — the whole money-moving sequence."""
    order = gateway.create_order(
        amount_paise=amount_paise,
        currency="INR",
        receipt=request_id,
        idempotency_key=f"{request_id}:order",
    )
    ledger.append(
        EventType.PAYMENT_INITIATED,
        request_id,
        observed={"gateway": gateway.name, **order.as_observed()},
    )
    payment = gateway.capture(order, idempotency_key=f"{request_id}:capture")
    ledger.append(
        EventType.PAYMENT_SETTLED if payment.settled else EventType.PAYMENT_FAILED,
        request_id,
        observed={"gateway": gateway.name, **payment.as_observed()},
    )
    return order, payment


def test_a_settlement_leaves_a_verifiable_trail(rig):
    ledger, gateway = rig
    total = parse_paise("₹1,999.00")

    ledger.append(
        EventType.INTENT_RECEIVED,
        "req-1",
        observed={"goal": "ingredients for a thai curry", "budget_paise": parse_paise("₹2,000")},
    )
    ledger.append(
        EventType.DECISION_MADE,
        "req-1",
        observed={"cart_total_paise": total, "snapshot_hash": "a" * 64},
        inferred={"outcome": "approve", "confidence_bp": 9_200},
    )
    _, payment = settle(ledger, gateway, "req-1", total)

    assert payment.status is PaymentStatus.CAPTURED
    result = verify_chain(ledger)
    assert result.ok, str(result)

    trail = ledger.read("req-1")
    assert [e.event_type for e in trail] == [
        EventType.INTENT_RECEIVED,
        EventType.DECISION_MADE,
        EventType.PAYMENT_INITIATED,
        EventType.PAYMENT_SETTLED,
    ]
    assert trail[0].prev_hash == GENESIS_HASH
    assert all(b.prev_hash == a.hash for a, b in zip(trail, trail[1:]))


def test_the_ledger_records_the_amount_the_gateway_saw_not_the_one_we_meant(rig):
    """Evidence is what happened. `observed` is populated from the response."""
    ledger, gateway = rig
    order, payment = settle(ledger, gateway, "req-1", parse_paise("₹1,999.00"))

    settled = ledger.read("req-1")[-1]
    assert settled.observed["amount_paise"] == 199_900
    assert settled.observed["payment_id"] == payment.payment_id
    assert settled.observed["gateway"] == "fake"
    assert settled.inferred == {}  # a settlement infers nothing


def test_a_failed_settlement_is_recorded_as_failed(rig):
    ledger, gateway = rig
    gateway.fail_order_ids.add("order_fake_000001")

    _, payment = settle(ledger, gateway, "req-1", parse_paise("₹1,999.00"))

    assert not payment.settled
    last = ledger.read("req-1")[-1]
    assert last.event_type is EventType.PAYMENT_FAILED
    assert last.observed["failure_reason"]
    assert verify_chain(ledger).ok


def test_a_retried_settlement_pays_once_and_records_once_more(rig):
    """The agent retries. The money moves once; the retry is still evidence."""
    ledger, gateway = rig
    total = parse_paise("₹1,999.00")

    _, first = settle(ledger, gateway, "req-1", total)
    _, second = settle(ledger, gateway, "req-1", total)

    assert first.payment_id == second.payment_id  # one payment
    events = ledger.read("req-1")
    assert len(events) == 4  # both attempts recorded — the ledger hides nothing
    assert sum(e.event_type is EventType.PAYMENT_SETTLED for e in events) == 2
    assert verify_chain(ledger).ok


def test_two_requests_cannot_both_capture_one_order(rig):
    """A fresh idempotency key is not a second route to the same money."""
    ledger, gateway = rig
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="req-1", idempotency_key="a:order"
    )
    gateway.capture(order, idempotency_key="a:capture")
    with pytest.raises(AlreadyCaptured):
        gateway.capture(order, idempotency_key="b:capture")


def test_interleaved_requests_share_one_unforked_chain(rig):
    ledger, gateway = rig
    for request_id in ("req-A", "req-B", "req-C"):
        settle(ledger, gateway, request_id, parse_paise("₹100"))

    assert verify_chain(ledger).ok
    assert len(ledger) == 6
    assert len(ledger.read("req-B")) == 2
