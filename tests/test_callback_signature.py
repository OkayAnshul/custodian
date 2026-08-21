"""The Checkout callback signature.

When a payment completes, the browser hands back an order id, a payment id and a
signature. The browser is an untrusted client — the same assumption this system
makes about the buying agent — so none of that is evidence until the signature
checks out. Without it, anyone who can reach the confirm endpoint could claim
any order was paid.

The signature is HMAC-SHA256(order_id|payment_id) under the key secret, so only
Razorpay and this server can produce one. That is testable without a browser,
and it is the half that matters.
"""

import hashlib
import hmac

import pytest
import razorpay

from custodian.payments.razorpay_client import RazorpayGateway

SECRET = "test_secret_value"
ORDER = "order_TSQ9ta0SoImmRF"
PAYMENT = "pay_ABCDEF123456"


@pytest.fixture
def gateway():
    return RazorpayGateway(client=razorpay.Client(auth=("rzp_test_stub", SECRET)))


def sign(order_id: str, payment_id: str, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


def test_a_genuine_callback_verifies(gateway):
    assert gateway.verify_callback(order_id=ORDER, payment_id=PAYMENT,
                                   signature=sign(ORDER, PAYMENT))


def test_a_forged_signature_is_refused(gateway):
    assert not gateway.verify_callback(order_id=ORDER, payment_id=PAYMENT,
                                       signature="deadbeef" * 8)


def test_a_signature_for_a_different_order_is_refused(gateway):
    """Replaying a real signature against another order must not work."""
    assert not gateway.verify_callback(order_id="order_SOMETHING_ELSE",
                                       payment_id=PAYMENT,
                                       signature=sign(ORDER, PAYMENT))


def test_a_signature_for_a_different_payment_is_refused(gateway):
    assert not gateway.verify_callback(order_id=ORDER, payment_id="pay_OTHER",
                                       signature=sign(ORDER, PAYMENT))


def test_a_signature_made_with_the_wrong_secret_is_refused(gateway):
    """Someone who knows both ids and not the secret still cannot produce one."""
    assert not gateway.verify_callback(order_id=ORDER, payment_id=PAYMENT,
                                       signature=sign(ORDER, PAYMENT, "not_the_secret"))


def test_an_invalid_signature_is_an_outcome_not_an_exception(gateway):
    """It gets recorded and refused, rather than crashing the request."""
    assert gateway.verify_callback(order_id=ORDER, payment_id=PAYMENT,
                                   signature="x" * 64) is False
