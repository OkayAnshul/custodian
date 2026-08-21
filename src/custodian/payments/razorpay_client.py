"""The live Razorpay gateway, test mode.

Built on the Orders API, which is Razorpay's canonical primitive: an order is
the thing a payment attaches to, and its id is what the ledger records.

Payment Links were tried first, because a link yields a payable URL from a
server-side call alone and needs no hosted page. Measured against test-mode
credentials, they are rate limited hard enough to be unusable as a per-order
primitive — three creations in a burst, then "Too many requests" — while the
Orders API took the same burst without complaint. So links are minted on demand
by ``payment_link_for`` when a human actually needs to pay, and are not on the
path of every order. See BROKE.md 006.

**What is real and what is not**, stated plainly because the distinction is the
kind a reviewer is entitled to check: order creation, the payable link, payment
fetch and capture are all live calls against Razorpay's test-mode API, and the
payment ids in the ledger are Razorpay's. Completing a payment still requires a
human on the hosted page with a test card — there is no server-side call that
makes a payment happen, which is the same gap ``FakeGateway.simulate_payer``
stands in for. The UPI mandate envelope is modelled locally and is not a
Razorpay call at all (see ``schemas/mandate.py``).

The single control that matters here: the order is created for the gate's
``verified_total_paise``, never for the agent's asserted total. Whatever the
agent claimed, the payable amount is the one Custodian re-derived from the
catalog.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from custodian.money import MoneyError
from custodian.payments.gateway import (
    AlreadyCaptured,
    IdempotencyConflict,
    OrderRef,
    PaymentError,
    PaymentRef,
    PaymentStatus,
)

#: Razorpay payment states, mapped onto ours. Anything unrecognised is treated
#: as FAILED rather than assumed benign.
_STATUS = {
    "created": PaymentStatus.CREATED,
    "authorized": PaymentStatus.AUTHORIZED,
    "captured": PaymentStatus.CAPTURED,
    "refunded": PaymentStatus.CAPTURED,
    "failed": PaymentStatus.FAILED,
}


@dataclass
class RazorpayGateway:
    """Razorpay test mode, behind the same Protocol as the fake."""

    key_id: str | None = None
    key_secret: str | None = None
    client: Any = field(default=None, repr=False)
    _idempotency: dict[str, tuple[str, Any]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        key_id = self.key_id or os.environ.get("RAZORPAY_KEY_ID")
        key_secret = self.key_secret or os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise PaymentError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required; "
                "use FakeGateway for offline work"
            )
        if not key_id.startswith("rzp_test_"):
            # A live key in this codebase would move real money on a decision
            # made by an untuned gate. Refusing is cheaper than trusting config.
            raise PaymentError(f"refusing a non-test Razorpay key: {key_id[:9]}…")
        try:
            import razorpay
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise PaymentError("the razorpay package is required for live settlement") from exc
        self.client = razorpay.Client(auth=(key_id, key_secret))
        # Off by default in the SDK. Test-mode payment-link creation is rate
        # limited tightly enough that a burst of orders hits it, and a 429 is a
        # transport condition rather than a decision about the payment — the one
        # class of failure it is safe to retry, because no money has moved.
        self.client.enable_retry(True)

    @property
    def name(self) -> str:
        return "razorpay-test"

    # --- the Protocol ------------------------------------------------------

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, idempotency_key: str
    ) -> OrderRef:
        if isinstance(amount_paise, float):
            raise MoneyError("amount_paise must be int paise, not float")
        if amount_paise <= 0:
            raise PaymentError(f"order amount must be positive, got {amount_paise}")
        if not idempotency_key:
            raise PaymentError("idempotency_key is required")

        fingerprint = _fingerprint(amount_paise, currency, receipt)
        if (replayed := self._replay(idempotency_key, fingerprint)) is not None:
            return replayed

        raw = self._call(
            "create order",
            lambda: self.client.order.create(
                {
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": _reference_id(receipt),
                    "notes": {"custodian_receipt": receipt[:512]},
                }
            ),
        )
        order = OrderRef(
            order_id=str(raw["id"]),
            amount_paise=int(raw["amount"]),
            currency=str(raw["currency"]),
            receipt=receipt,
            payment_url=None,  # minted on demand — see payment_link_for
        )
        self._idempotency[idempotency_key] = (fingerprint, order)
        return order

    def payment_for(self, order: OrderRef) -> PaymentRef | None:
        listing = self._call(
            "fetch order payments", lambda: self.client.order.payments(order.order_id)
        )
        entries = listing.get("items") or []
        if not entries:
            return None
        # Prefer a payment we can still act on; fall back to the most recent.
        for entry in entries:
            if entry.get("status") in ("authorized", "captured"):
                return _to_payment(entry, order.order_id)
        return _to_payment(entries[-1], order.order_id)

    def payment_link_for(self, order: OrderRef) -> str:
        """Mint a payable URL for an order. Called when a human needs to pay.

        Deliberately not part of ``create_order``. Payment-link creation is rate
        limited far more tightly than order creation, and putting it on the path
        of every order would make the limit a property of the system rather than
        of the moment someone actually pays.

        Note the seam this leaves: Razorpay links carry their own order, so the
        payment lands against the link rather than against ``order``. It is a
        demo affordance, not a settlement path — the settlement path is Checkout
        against ``order.order_id``, which the replay viewer hosts.
        """
        link = self._call(
            "create payment link",
            lambda: self.client.payment_link.create(
                {
                    "amount": order.amount_paise,
                    "currency": order.currency,
                    "description": f"Custodian verified order {order.receipt}",
                    "reference_id": _reference_id(f"{order.receipt}-link"),
                    "accept_partial": False,
                    "notify": {"sms": False, "email": False},
                    "notes": {"custodian_order": order.order_id},
                }
            ),
        )
        return str(link["short_url"])

    def capture(self, payment: PaymentRef, *, idempotency_key: str) -> PaymentRef:
        if not idempotency_key:
            raise PaymentError("idempotency_key is required")

        fingerprint = _fingerprint(payment.payment_id, payment.amount_paise)
        if (replayed := self._replay(idempotency_key, fingerprint)) is not None:
            return replayed

        current = self.fetch(payment.payment_id)
        if current.status is PaymentStatus.CAPTURED:
            raise AlreadyCaptured(f"payment {payment.payment_id} has already been captured")
        if current.status is not PaymentStatus.AUTHORIZED:
            raise PaymentError(
                f"payment {payment.payment_id} is {current.status}, not authorised — "
                "there is nothing to capture"
            )

        # Capture exactly what was authorised. Razorpay takes the amount
        # explicitly, and passing anything else here would charge an amount no
        # decision approved.
        raw = self._call(
            "capture payment",
            lambda: self.client.payment.capture(
                payment.payment_id, current.amount_paise, {"currency": payment.currency_or_inr}
            ),
        )
        captured = _to_payment(raw, payment.order_id)
        self._idempotency[idempotency_key] = (fingerprint, captured)
        return captured

    def verify_callback(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        """Whether a Checkout callback genuinely came from Razorpay.

        When a payment completes, the browser hands back an order id, a payment
        id and a signature. The browser is an untrusted client — the same
        assumption this whole system makes about the buying agent — so the
        callback is not evidence until the signature checks out.

        The signature is ``HMAC-SHA256(order_id|payment_id)`` under the key
        secret, so only Razorpay and this server can produce it. Without this
        check, anyone who can POST to the confirm endpoint can claim any order
        was paid.

        Returns ``False`` rather than raising: an invalid signature is an
        outcome to record, not an exception to swallow.
        """
        import razorpay.errors

        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
        except razorpay.errors.SignatureVerificationError:
            return False
        except Exception as exc:  # a malformed field, not a valid-but-wrong one
            raise PaymentError(f"razorpay: could not verify callback: {exc}") from exc
        return True

    def fetch(self, payment_id: str) -> PaymentRef:
        raw = self._call("fetch payment", lambda: self.client.payment.fetch(payment_id))
        return _to_payment(raw, order_id=str(raw.get("order_id") or ""))

    # --- internals ---------------------------------------------------------

    def _payment(self, payment_id: str, order_id: str) -> PaymentRef:
        raw = self._call("fetch payment", lambda: self.client.payment.fetch(payment_id))
        return _to_payment(raw, order_id)

    def _replay(self, key: str, fingerprint: str) -> Any | None:
        if key not in self._idempotency:
            return None
        recorded, result = self._idempotency[key]
        if recorded != fingerprint:
            raise IdempotencyConflict(
                f"idempotency key {key!r} was already used with different arguments"
            )
        return result

    @staticmethod
    def _call(what: str, fn, *, attempts: int = 4):
        """Run a provider call, turning transport failures into PaymentError.

        A network problem and a declined payment are different things, and
        collapsing them would let a timeout read as a refusal.

        Rate limiting is retried here rather than left to the SDK. Razorpay
        reports "Too many requests" as a ``BadRequestError`` — a 400-class
        exception — so the SDK's own backoff, which keys on status class, does
        not catch it. It is nonetheless the one failure that is unambiguously
        safe to retry: the request was refused before anything happened, so no
        money moved and no state changed.
        """
        import time

        delay = 1.0
        for attempt in range(attempts):
            try:
                return fn()
            except Exception as exc:
                if type(exc).__name__ in ("AlreadyCaptured", "IdempotencyConflict"):
                    raise
                if _is_rate_limit(exc) and attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise PaymentError(
                    f"razorpay: could not {what}: {type(exc).__name__}: {exc}"
                ) from exc


#: Razorpay caps reference_id at 40 characters. A Custodian receipt is a
#: request id, which has no such limit, so it is shortened here rather than
#: constrained upstream — a provider's field length should not reach back and
#: dictate the shape of our own identifiers.
_REFERENCE_ID_MAX = 40


def _reference_id(receipt: str) -> str:
    """A provider-compliant reference for ``receipt``, stable across retries.

    Short receipts pass through unchanged so they stay readable in the Razorpay
    dashboard. Longer ones become a deterministic digest — deterministic because
    an idempotent retry must produce the same reference, and a truncation would
    silently collide two different long receipts sharing a prefix.
    """
    import hashlib

    if len(receipt) <= _REFERENCE_ID_MAX:
        return receipt
    return "cst_" + hashlib.sha256(receipt.encode()).hexdigest()[:36]


def _is_rate_limit(exc: Exception) -> bool:
    """Whether a provider exception is a rate limit, by any of its spellings."""
    text = str(exc).lower()
    return "too many requests" in text or "rate limit" in text or "429" in text


def _fingerprint(*parts: object) -> str:
    import hashlib

    return hashlib.sha256("|".join(repr(p) for p in parts).encode()).hexdigest()


def _to_payment(raw: dict, order_id: str) -> PaymentRef:
    status = _STATUS.get(str(raw.get("status")), PaymentStatus.FAILED)
    return PaymentRef(
        payment_id=str(raw["id"]),
        order_id=order_id,
        amount_paise=int(raw["amount"]),
        status=status,
        failure_reason=raw.get("error_description") if status is PaymentStatus.FAILED else None,
    )
