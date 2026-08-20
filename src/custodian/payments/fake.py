"""In-process payment gateway for tests, the eval harness, and offline demos.

It is not a mock in the usual sense — it enforces the same idempotency and
state-transition rules the real gateway must, so a bug in Custodian's settlement
logic fails here rather than surfacing for the first time against live test-mode
credentials.

``fail_order_ids`` makes settlement failure reproducible, which the recovery
path and the demo's failure story both need.
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
    _captured_orders: set[str] = field(default_factory=set, repr=False)

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

        order = OrderRef(
            order_id=f"order_fake_{len(self._orders) + 1:06d}",
            amount_paise=amount_paise,
            currency=currency,
            receipt=receipt,
        )
        self._orders[order.order_id] = order
        self._idempotency[idempotency_key] = (fingerprint, order)
        return order

    def capture(self, order: OrderRef, *, idempotency_key: str) -> PaymentRef:
        if not idempotency_key:
            raise PaymentError("idempotency_key is required")
        if order.order_id not in self._orders:
            raise PaymentError(f"unknown order: {order.order_id}")

        fingerprint = self._fingerprint(order.order_id, order.amount_paise)
        if (replayed := self._replay(idempotency_key, fingerprint)) is not None:
            return replayed  # type: ignore[return-value]

        # A fresh idempotency key must not be a second route to the same money.
        if order.order_id in self._captured_orders:
            raise AlreadyCaptured(f"order {order.order_id} has already been captured")

        failed = order.order_id in self.fail_order_ids
        payment = PaymentRef(
            payment_id=f"pay_fake_{len(self._payments) + 1:06d}",
            order_id=order.order_id,
            amount_paise=order.amount_paise,
            status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED,
            failure_reason="simulated gateway failure" if failed else None,
        )
        self._payments[payment.payment_id] = payment
        self._idempotency[idempotency_key] = (fingerprint, payment)
        if payment.settled:
            self._captured_orders.add(order.order_id)
        return payment

    def fetch(self, payment_id: str) -> PaymentRef:
        if payment_id not in self._payments:
            raise PaymentError(f"unknown payment: {payment_id}")
        return self._payments[payment_id]
