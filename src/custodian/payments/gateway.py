"""The payment boundary.

Custodian talks to exactly one payment interface. The real Razorpay client and
the in-process fake both satisfy it and both pass the same contract test suite,
so the gate, the ledger and the demo can be built and verified before any live
credential exists — and so a credential problem on the day can never be
mistaken for a logic problem.

Idempotency is part of the interface, not an implementation detail. An agent
that retries a settlement must not be able to pay twice, and "we won't retry" is
not a control. Replaying a key with the *same* arguments returns the original
result; replaying it with different arguments is a caller bug and raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"


class PaymentError(RuntimeError):
    """A settlement could not be completed."""


class IdempotencyConflict(PaymentError):
    """An idempotency key was reused with different arguments."""


class AlreadyCaptured(PaymentError):
    """A second capture was attempted on an order that has already been paid.

    Distinct from ``IdempotencyConflict``: an idempotency key protects a *retry*
    of the same call, while this protects against two different calls both
    moving money for one order. An agent that can produce two idempotency keys
    would otherwise be able to pay twice.
    """


@dataclass(frozen=True, slots=True)
class OrderRef:
    """A created order, not yet paid."""

    order_id: str
    amount_paise: int
    currency: str
    receipt: str

    def as_observed(self) -> dict[str, object]:
        """The ledger-safe view: what the gateway told us, nothing derived."""
        return {
            "order_id": self.order_id,
            "amount_paise": self.amount_paise,
            "currency": self.currency,
            "receipt": self.receipt,
        }


@dataclass(frozen=True, slots=True)
class PaymentRef:
    """The outcome of attempting to move money."""

    payment_id: str
    order_id: str
    amount_paise: int
    status: PaymentStatus
    failure_reason: str | None = None

    @property
    def settled(self) -> bool:
        return self.status is PaymentStatus.CAPTURED

    def as_observed(self) -> dict[str, object]:
        return {
            "payment_id": self.payment_id,
            "order_id": self.order_id,
            "amount_paise": self.amount_paise,
            "status": str(self.status),
            "failure_reason": self.failure_reason,
        }


@runtime_checkable
class PaymentGateway(Protocol):
    """What Custodian requires of a payment provider. Deliberately small."""

    @property
    def name(self) -> str:
        """Identifier recorded in the ledger, so evidence names its source."""
        ...

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, idempotency_key: str
    ) -> OrderRef:
        """Reserve an order for ``amount_paise``. Idempotent on ``idempotency_key``."""
        ...

    def capture(self, order: OrderRef, *, idempotency_key: str) -> PaymentRef:
        """Move the money.

        Idempotent on ``idempotency_key``. An order that has already been
        captured raises ``AlreadyCaptured`` even under a fresh key.
        """
        ...

    def fetch(self, payment_id: str) -> PaymentRef:
        """Current state of a payment, as the provider reports it."""
        ...
