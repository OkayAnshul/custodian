"""In-process payment gateway for tests, the eval harness, and offline demos.

It is not a mock in the usual sense — it enforces the same idempotency and
state-transition rules the real gateway must, so a bug in Custodian's settlement
logic fails here rather than surfacing for the first time against live test-mode
credentials.

``fail_order_ids`` makes settlement failure reproducible, which the recovery
path and the demo's failure story both need.

``simulate_payer`` stands in for the step a human performs on a hosted checkout
page. It exists because the real lifecycle has a gap in it that no API call
closes — see ``gateway.PaymentGateway`` — and pretending otherwise here would
mean the fake passed a contract the real gateway could not.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from custodian.money import MoneyError
from custodian.payments.gateway import (
    AlreadyCaptured,
    IdempotencyConflict,
    OrderRef,
    PaymentError,
    PaymentRef,
    PaymentStatus,
)


@dataclass
class FakeGateway:
    """A deterministic stand-in for a real payment provider."""

    #: Order ids whose capture should fail, to exercise the recovery path.
    fail_order_ids: set[str] = field(default_factory=set)

    _orders: dict[str, OrderRef] = field(default_factory=dict, repr=False)
    _payments: dict[str, PaymentRef] = field(default_factory=dict, repr=False)
    _idempotency: dict[str, tuple[str, object]] = field(default_factory=dict, repr=False)
    _captured: set[str] = field(default_factory=set, repr=False)
    _authorized_by_order: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def name(self) -> str:
        return "fake"

    @staticmethod
    def _fingerprint(*parts: object) -> str:
        """Arguments a replayed idempotency key must match."""
        return hashlib.sha256("|".join(repr(p) for p in parts).encode()).hexdigest()

    def _replay(self, key: str, fingerprint: str) -> object | None:
        """Return the recorded result for ``key``, or raise if arguments differ."""
        if key not in self._idempotency:
            return None
        recorded_fingerprint, result = self._idempotency[key]
        if recorded_fingerprint != fingerprint:
            raise IdempotencyConflict(
                f"idempotency key {key!r} was already used with different arguments"
            )
        return result

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, idempotency_key: str
    ) -> OrderRef:
        if isinstance(amount_paise, float):
            raise MoneyError("amount_paise must be int paise, not float")
        if amount_paise <= 0:
            raise PaymentError(f"order amount must be positive, got {amount_paise}")
        if not idempotency_key:
            raise PaymentError("idempotency_key is required")

        fingerprint = self._fingerprint(amount_paise, currency, receipt)
        if (replayed := self._replay(idempotency_key, fingerprint)) is not None:
            return replayed  # type: ignore[return-value]

        order_id = f"order_fake_{len(self._orders) + 1:06d}"
        order = OrderRef(
            order_id=order_id,
            amount_paise=amount_paise,
            currency=currency,
            receipt=receipt,
            payment_url=f"https://fake.invalid/pay/{order_id}",
        )
        self._orders[order.order_id] = order
        self._idempotency[idempotency_key] = (fingerprint, order)
        return order

    def simulate_payer(self, order: OrderRef, *, amount_paise: int | None = None) -> PaymentRef:
        """Stand in for a human completing checkout. Tests and demos only.

        ``amount_paise`` defaults to the order amount; passing a different value
        models an underpayment, which the capture path must refuse.
        """
        if order.order_id not in self._orders:
            raise PaymentError(f"unknown order: {order.order_id}")
        payment = PaymentRef(
            payment_id=f"pay_fake_{len(self._payments) + 1:06d}",
            order_id=order.order_id,
            amount_paise=order.amount_paise if amount_paise is None else amount_paise,
            status=PaymentStatus.AUTHORIZED,
        )
        self._payments[payment.payment_id] = payment
        self._authorized_by_order[order.order_id] = payment.payment_id
        return payment

    def payment_for(self, order: OrderRef) -> PaymentRef | None:
        payment_id = self._authorized_by_order.get(order.order_id)
        return self._payments[payment_id] if payment_id else None

    def capture(self, payment: PaymentRef, *, idempotency_key: str) -> PaymentRef:
        if not idempotency_key:
            raise PaymentError("idempotency_key is required")
        if payment.payment_id not in self._payments:
            raise PaymentError(f"unknown payment: {payment.payment_id}")

        fingerprint = self._fingerprint(payment.payment_id, payment.amount_paise)
        if (replayed := self._replay(idempotency_key, fingerprint)) is not None:
            return replayed  # type: ignore[return-value]

        # A fresh idempotency key must not be a second route to the same money.
        if payment.payment_id in self._captured:
            raise AlreadyCaptured(f"payment {payment.payment_id} has already been captured")

        failed = payment.order_id in self.fail_order_ids
        captured = PaymentRef(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            amount_paise=payment.amount_paise,
            status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED,
            failure_reason="simulated gateway failure" if failed else None,
        )
        self._payments[captured.payment_id] = captured
        self._idempotency[idempotency_key] = (fingerprint, captured)
        if captured.settled:
            self._captured.add(captured.payment_id)
        return captured

    def fetch(self, payment_id: str) -> PaymentRef:
        if payment_id not in self._payments:
            raise PaymentError(f"unknown payment: {payment_id}")
        return self._payments[payment_id]
