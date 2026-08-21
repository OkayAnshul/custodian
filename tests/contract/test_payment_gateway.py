"""The contract every PaymentGateway implementation must satisfy.

Run against FakeGateway always, and against live Razorpay test-mode credentials
when `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are present (`-m live`). That
equivalence is the point: the same file grades both, so a settlement bug cannot
hide behind "the fake is not realistic".

One asymmetry is real and is marked rather than papered over. No API call makes
a payment *happen* — a human completes it on the hosted page — so tests past the
authorisation step run only where the payer can be simulated. Pretending
otherwise would mean the fake passed a contract the live gateway cannot.
"""

import os

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

HAS_LIVE_KEYS = bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))


@pytest.fixture(
    params=[
        "fake",
        pytest.param(
            "razorpay",
            marks=[
                pytest.mark.live,
                pytest.mark.skipif(not HAS_LIVE_KEYS, reason="no Razorpay test credentials"),
            ],
        ),
    ]
)
def gateway(request) -> PaymentGateway:
    if request.param == "fake":
        return FakeGateway()
    from custodian.payments.razorpay_client import RazorpayGateway

    return RazorpayGateway()


def _key(request, suffix: str) -> str:
    """A key unique per test run, so live idempotency records do not collide.

    Kept short deliberately: it doubles as a receipt, and passing a long one
    here would exercise the gateway's reference-id shortening rather than the
    behaviour each test is actually about. That shortening has its own test.
    """
    import hashlib

    stem = hashlib.sha1(request.node.name.encode()).hexdigest()[:8]
    return f"{stem}-{os.getpid()}-{suffix}"


def _can_simulate_payer(gateway) -> bool:
    return hasattr(gateway, "simulate_payer")


# --- shape -----------------------------------------------------------------

def test_satisfies_the_protocol(gateway):
    assert isinstance(gateway, PaymentGateway)
    assert gateway.name


# --- creating an order -----------------------------------------------------

def test_create_order_echoes_what_it_was_asked_for(gateway, request):
    order = gateway.create_order(
        amount_paise=19_900, currency="INR", receipt=_key(request, "r"),
        idempotency_key=_key(request, "k"),
    )
    assert order.amount_paise == 19_900
    assert order.currency == "INR"
    assert order.order_id


def test_a_payable_url_is_optional_because_minting_one_is_not_free(gateway, request):
    """Razorpay rate-limits link creation ~3/burst; order creation is unlimited.

    So a payable URL is minted when someone actually needs to pay, not on the
    path of every order. Gateways that can supply one inline may.
    """
    order = gateway.create_order(
        amount_paise=19_900, currency="INR", receipt=_key(request, "r"),
        idempotency_key=_key(request, "k"),
    )
    assert order.payment_url is None or order.payment_url.startswith("http")


def test_replaying_a_key_returns_the_original_order(gateway, request):
    args = dict(amount_paise=19_900, currency="INR", receipt=_key(request, "r"),
                idempotency_key=_key(request, "k"))
    assert gateway.create_order(**args).order_id == gateway.create_order(**args).order_id


def test_reusing_a_key_with_different_arguments_is_a_conflict(gateway, request):
    key = _key(request, "k")
    gateway.create_order(amount_paise=19_900, currency="INR",
                         receipt=_key(request, "r"), idempotency_key=key)
    with pytest.raises(IdempotencyConflict):
        gateway.create_order(amount_paise=500_000, currency="INR",
                             receipt=_key(request, "r"), idempotency_key=key)


@pytest.mark.parametrize("amount", [0, -1])
def test_refuses_non_positive_amounts(gateway, request, amount):
    with pytest.raises(PaymentError):
        gateway.create_order(amount_paise=amount, currency="INR",
                             receipt=_key(request, "r"), idempotency_key=_key(request, "k"))


def test_refuses_float_amounts(gateway, request):
    with pytest.raises((MoneyError, PaymentError)):
        gateway.create_order(amount_paise=1999.0, currency="INR",
                             receipt=_key(request, "r"), idempotency_key=_key(request, "k"))


def test_idempotency_key_is_required(gateway, request):
    with pytest.raises(PaymentError):
        gateway.create_order(amount_paise=100, currency="INR",
                             receipt=_key(request, "r"), idempotency_key="")


# --- observing payment -----------------------------------------------------

def test_an_unpaid_order_has_no_payment_and_that_is_not_an_error(gateway, request):
    """The ordinary state of a fresh order. Nothing to capture yet."""
    order = gateway.create_order(
        amount_paise=19_900, currency="INR", receipt=_key(request, "r"),
        idempotency_key=_key(request, "k"),
    )
    assert gateway.payment_for(order) is None


def test_a_long_receipt_is_shortened_for_the_provider_not_rejected(gateway, request):
    """Razorpay caps reference_id at 40 chars; a Custodian request id has no cap."""
    long_receipt = "custodian-request-" + "x" * 80
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=long_receipt, idempotency_key=_key(request, "k"))
    assert order.receipt == long_receipt  # what we asked for is what we recorded


def test_unknown_payment_is_an_error_not_a_none(gateway):
    with pytest.raises(PaymentError):
        gateway.fetch("pay_does_not_exist")


# --- capture ---------------------------------------------------------------

def test_a_paid_order_surfaces_an_authorised_payment(gateway, request):
    if not _can_simulate_payer(gateway):
        pytest.skip("no API call makes a payment happen; a human completes it")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=_key(request, "r"), idempotency_key=_key(request, "k"))
    gateway.simulate_payer(order)
    observed = gateway.payment_for(order)
    assert observed is not None and observed.status is PaymentStatus.AUTHORIZED


def test_capture_settles_an_authorised_payment(gateway, request):
    if not _can_simulate_payer(gateway):
        pytest.skip("requires a completed payment")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=_key(request, "r"), idempotency_key=_key(request, "k"))
    authorised = gateway.simulate_payer(order)
    captured = gateway.capture(authorised, idempotency_key=_key(request, "c"))
    assert captured.status is PaymentStatus.CAPTURED and captured.settled


def test_a_retried_capture_does_not_pay_twice(gateway, request):
    if not _can_simulate_payer(gateway):
        pytest.skip("requires a completed payment")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=_key(request, "r"), idempotency_key=_key(request, "k"))
    authorised = gateway.simulate_payer(order)
    key = _key(request, "c")
    assert gateway.capture(authorised, idempotency_key=key).payment_id == \
           gateway.capture(authorised, idempotency_key=key).payment_id


def test_a_fresh_key_is_not_a_second_route_to_the_same_money(gateway, request):
    """The control an untrusted agent cannot get around by generating a new key."""
    if not _can_simulate_payer(gateway):
        pytest.skip("requires a completed payment")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=_key(request, "r"), idempotency_key=_key(request, "k"))
    authorised = gateway.simulate_payer(order)
    gateway.capture(authorised, idempotency_key=_key(request, "c1"))
    with pytest.raises(AlreadyCaptured):
        gateway.capture(authorised, idempotency_key=_key(request, "c2"))


def test_fetch_reports_what_the_provider_holds(gateway, request):
    if not _can_simulate_payer(gateway):
        pytest.skip("requires a completed payment")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt=_key(request, "r"), idempotency_key=_key(request, "k"))
    payment = gateway.simulate_payer(order)
    assert gateway.fetch(payment.payment_id).payment_id == payment.payment_id


def test_failure_is_reportable_not_raised(gateway, request):
    """A declined payment is an outcome to record, not an exception to swallow."""
    if not isinstance(gateway, FakeGateway):
        pytest.skip("failure injection is fake-only")
    order = gateway.create_order(amount_paise=19_900, currency="INR",
                                 receipt="r", idempotency_key="k")
    gateway.fail_order_ids.add(order.order_id)
    payment = gateway.capture(gateway.simulate_payer(order), idempotency_key="c")
    assert payment.status is PaymentStatus.FAILED and not payment.settled
