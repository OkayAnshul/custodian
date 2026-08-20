"""The contract every PaymentGateway implementation must satisfy.

FakeGateway passes it today. RazorpayGateway must pass this same file, unchanged,
against live test-mode credentials — that equivalence is what makes the Day 5
checkpoint a credential question rather than a logic question.
"""

import pytest

from custodian.money import MoneyError
from custodian.payments.fake import FakeGateway
from custodian.payments.gateway import (
    AlreadyCaptured,
    IdempotencyConflict,
    PaymentError,
    PaymentGateway,
    PaymentStatus,
)

pytestmark = pytest.mark.contract


@pytest.fixture(params=["fake"])
def gateway(request) -> PaymentGateway:
    """Every implementation is added here and must pass everything below."""
    if request.param == "fake":
        return FakeGateway()
    raise AssertionError(f"no such gateway: {request.param}")


def test_satisfies_the_protocol(gateway):
    assert isinstance(gateway, PaymentGateway)
    assert gateway.name


def test_create_order_echoes_what_it_was_asked_for(gateway):
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="req-1", idempotency_key="k1"
    )
    assert order.amount_paise == 199_900
    assert order.currency == "INR"
    assert order.receipt == "req-1"
    assert order.order_id


def test_replaying_a_key_returns_the_original_order(gateway):
    args = dict(amount_paise=199_900, currency="INR", receipt="req-1", idempotency_key="k1")
    assert gateway.create_order(**args).order_id == gateway.create_order(**args).order_id


def test_reusing_a_key_with_different_arguments_is_a_conflict(gateway):
    gateway.create_order(amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1")
    with pytest.raises(IdempotencyConflict):
        gateway.create_order(amount_paise=500_000, currency="INR", receipt="r", idempotency_key="k1")


def test_capture_settles_the_order(gateway):
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1"
    )
    payment = gateway.capture(order, idempotency_key="c1")
    assert payment.status is PaymentStatus.CAPTURED
    assert payment.settled
    assert payment.amount_paise == order.amount_paise


def test_a_retried_capture_does_not_pay_twice(gateway):
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1"
    )
    first = gateway.capture(order, idempotency_key="c1")
    second = gateway.capture(order, idempotency_key="c1")
    assert first.payment_id == second.payment_id


def test_a_fresh_key_is_not_a_second_route_to_the_same_money(gateway):
    """The control an agent cannot get around by generating a new key."""
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1"
    )
    gateway.capture(order, idempotency_key="c1")
    with pytest.raises(AlreadyCaptured):
        gateway.capture(order, idempotency_key="c2")


def test_fetch_reports_what_the_provider_holds(gateway):
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1"
    )
    payment = gateway.capture(order, idempotency_key="c1")
    assert gateway.fetch(payment.payment_id).payment_id == payment.payment_id


def test_unknown_payment_is_an_error_not_a_none(gateway):
    with pytest.raises(PaymentError):
        gateway.fetch("pay_does_not_exist")


@pytest.mark.parametrize("amount", [0, -1])
def test_refuses_non_positive_amounts(gateway, amount):
    with pytest.raises(PaymentError):
        gateway.create_order(amount_paise=amount, currency="INR", receipt="r", idempotency_key="k")


def test_refuses_float_amounts(gateway):
    with pytest.raises((MoneyError, PaymentError)):
        gateway.create_order(
            amount_paise=1999.0, currency="INR", receipt="r", idempotency_key="k"
        )


def test_idempotency_key_is_required(gateway):
    with pytest.raises(PaymentError):
        gateway.create_order(amount_paise=100, currency="INR", receipt="r", idempotency_key="")


def test_failure_is_reportable_not_raised(gateway):
    """A declined payment is an outcome to record, not an exception to swallow."""
    if not isinstance(gateway, FakeGateway):
        pytest.skip("failure injection is fake-only")
    order = gateway.create_order(
        amount_paise=199_900, currency="INR", receipt="r", idempotency_key="k1"
    )
    gateway.fail_order_ids.add(order.order_id)
    payment = gateway.capture(order, idempotency_key="c1")
    assert payment.status is PaymentStatus.FAILED
    assert not payment.settled
    assert payment.failure_reason
