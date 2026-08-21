"""The flow around the gate: evidence in, decision recorded, settlement gated.

``decide()`` is pure and knows nothing about storage, models or time. This is
where those live, arranged so that the pure function's inputs are all recorded
before it runs and its output is recorded after.

The order is the security property. Deterministic checks decide whether anything
needs escalating *before* a model is called, so a cart that fails on price costs
no tokens and a model never sees a case the arithmetic settled.

Re-confirmation does not change a decision. A held order stays held in the
record; what changes is who authorised settling it. "Custodian held this and a
human overrode it at 14:32" is the truthful entry, and rewriting the decision to
APPROVE would erase the fact that anyone had to be asked.

A rejection is final. A human may confirm something the gate was unsure about;
they may not confirm past a price mismatch or a spent mandate. A hard constraint
a human can wave through is advisory, and this system's whole claim is that
policy enforcement lives in infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from custodian.clock import utc_now
from custodian.gate.binding import bind
from custodian.gate.decide import decide, escalations
from custodian.gate.semantic import ScoringError, SemanticScorer
from custodian.gate.substitution import SubstitutionTables
from custodian.payments.gateway import AlreadyCaptured, OrderRef, PaymentError, PaymentRef
from custodian.gate.thresholds import Thresholds
from custodian.ledger.chain import EventType, Ledger, LedgerEvent
from custodian.ledger.store import ArtifactStore
from custodian.schemas.cart import Cart
from custodian.schemas.catalog import CatalogSnapshot
from custodian.schemas.decision import Decision, Outcome
from custodian.schemas.decision_input import DecisionInput
from custodian.schemas.intent import Intent
from custodian.schemas.mandate import Mandate
from custodian.schemas.verdict import SemanticVerdict


@dataclass(frozen=True, slots=True)
class Authority:
    """Whether this request may settle, and on whose say-so."""

    allowed: bool
    basis: Literal["APPROVED", "RECONFIRMED", "HELD", "REJECTED", "NO_DECISION"]
    amount_paise: int
    reason: str

    def __str__(self) -> str:
        verb = "may settle" if self.allowed else "may not settle"
        return f"{verb} ({self.basis}): {self.reason}"


class AmountMismatch(PaymentError):
    """A payment arrived for an amount no decision approved."""


@dataclass
class Custodian:
    """Evaluates purchases and records the evidence."""

    ledger: Ledger
    store: ArtifactStore
    tables: SubstitutionTables
    scorer: SemanticScorer | None = None

    def evaluate(
        self,
        *,
        request_id: str,
        intent: Intent,
        cart: Cart,
        snapshot: CatalogSnapshot,
        mandate: Mandate,
        thresholds: Thresholds,
        evaluated_at: str | None = None,
    ) -> Decision:
        """Run one purchase through the gate, recording everything it rested on."""
        moment = evaluated_at or utc_now()

        self.ledger.append(
            EventType.INTENT_RECEIVED, request_id,
            observed={
                "intent_id": intent.intent_id, "goal": intent.goal,
                "budget_paise": intent.budget_paise,
                "merchant_scope": list(intent.merchant_scope),
                "substitution_policy": str(intent.substitution_policy),
                "requested": [
                    {"line_id": i.line_id, "raw_text": i.raw_text, "quantity": i.quantity}
                    for i in intent.requested_items
                ],
            },
            inferred={
                # Base and form come from the taxonomy, not from the human's words
                # and not from the model — an inference, and recorded as one.
                "placements": [
                    {"line_id": i.line_id, "base": i.base, "form": i.form, "category": i.category}
                    for i in intent.requested_items
                ],
            },
        )

        self.store.put_snapshot(snapshot)
        self.ledger.append(
            EventType.SNAPSHOT_TAKEN, request_id,
            observed={
                "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest(),
                "merchant_id": snapshot.merchant_id, "taken_at": snapshot.taken_at,
                "items": len(snapshot.items), "lexicon_version": snapshot.lexicon_version,
            },
        )

        provisional = DecisionInput(
            request_id=request_id, evaluated_at=moment, intent=intent, cart=cart,
            snapshot=snapshot, mandate=mandate, thresholds=thresholds,
        )
        verdicts = self._resolve_escalations(provisional, request_id)

        final = provisional.model_copy(update={"semantic_verdicts": verdicts})
        decision = decide(final, tables=self.tables)

        input_digest = self.store.put_input(final)
        decision_digest = self.store.put(decision.canonical(), kind="decision")
        self.ledger.append(
            EventType.DECISION_MADE, request_id,
            observed={
                "input_digest": input_digest,
                "snapshot_digest": snapshot.digest(),
                "thresholds_digest": thresholds.digest(),
                "tables_version": self.tables.version,
                "semantic_verdicts": len(verdicts),
                "asserted_total_paise": cart.asserted_total_paise,
            },
            inferred={
                "decision_digest": decision_digest,
                "outcome": str(decision.outcome),
                "alignment_bp": decision.alignment_bp,
                "confidence_bp": decision.confidence_bp,
                "verified_total_paise": decision.verified_total_paise,
                "reason_codes": [str(c) for c in decision.reason_codes],
            },
        )
        return decision

    def _resolve_escalations(
        self, provisional: DecisionInput, request_id: str
    ) -> tuple[SemanticVerdict, ...]:
        """Ask the model about the lines deterministic logic could not settle.

        Returns empty when nothing needs escalating *or* when a hard constraint
        already failed — ``escalations()`` enforces the second, so the cost of a
        rejected cart is zero tokens.
        """
        needed = escalations(provisional, tables=self.tables)
        if not needed or self.scorer is None:
            return ()

        report = bind(
            provisional.intent, provisional.cart, provisional.snapshot,
            tables=self.tables, thresholds=provisional.thresholds,
        )
        verdicts: list[SemanticVerdict] = []
        for bound in report.lines:
            if bound.line.line_id not in needed or bound.requested is None:
                continue
            item = provisional.snapshot.find(bound.line.item_id)
            if item is None:
                continue
            try:
                verdict = self.scorer.score(
                    goal=provisional.intent.goal, requested=bound.requested,
                    offered=item, cart_line_id=bound.line.line_id,
                )
            except ScoringError as exc:
                # A scorer that fails is not a verdict of "fine". The line stays
                # unresolved, confidence drops, and the decision holds.
                self.ledger.append(
                    EventType.SEMANTIC_VERDICT, request_id,
                    observed={"cart_line_id": bound.line.line_id, "error": str(exc)[:512]},
                )
                continue
            verdicts.append(verdict)
            self.ledger.append(
                EventType.SEMANTIC_VERDICT, request_id,
                observed={
                    "cart_line_id": verdict.cart_line_id,
                    "requested_line_id": verdict.requested_line_id,
                    "model": verdict.model, "prompt_digest": verdict.prompt_digest,
                    "raw_response": verdict.raw_response, "obtained_at": verdict.obtained_at,
                },
                inferred={"label": str(verdict.label), "score_bp": verdict.score_bp},
            )
        return tuple(verdicts)

    # --- re-confirmation ---------------------------------------------------

    def request_reconfirmation(self, request_id: str, *, question: str) -> LedgerEvent:
        return self.ledger.append(
            EventType.RECONFIRM_REQUESTED, request_id, observed={"question": question[:1024]}
        )

    def reconfirm(self, request_id: str, *, actor: str, note: str = "") -> LedgerEvent:
        """Record a human authorising a held purchase.

        Refuses on a rejected request. A person may confirm something the gate
        was unsure about; they may not confirm past a spent mandate.
        """
        authority = self.settlement_authority(request_id)
        if authority.basis == "REJECTED":
            raise PermissionError(
                f"{request_id} was rejected on a hard constraint and cannot be re-confirmed: "
                f"{authority.reason}"
            )
        if authority.basis == "NO_DECISION":
            raise PermissionError(f"{request_id} has no decision to re-confirm")

        return self.ledger.append(
            EventType.RECONFIRM_GRANTED, request_id,
            observed={"actor": actor, "note": note[:1024], "granted_at": utc_now()},
        )

    def settlement_authority(self, request_id: str) -> Authority:
        """May this request settle, and on whose authority?"""
        events = self.ledger.read(request_id)
        decision_event = next(
            (e for e in reversed(events) if e.event_type is EventType.DECISION_MADE), None
        )
        if decision_event is None:
            return Authority(False, "NO_DECISION", 0, "no decision has been recorded")

        outcome = decision_event.inferred["outcome"]
        amount = int(decision_event.inferred["verified_total_paise"])

        if outcome == str(Outcome.REJECT):
            return Authority(False, "REJECTED", amount,
                             "a hard constraint failed; this cannot be overridden")
        if outcome == str(Outcome.APPROVE):
            return Authority(True, "APPROVED", amount, "every check passed")

        granted = [
            e for e in events
            if e.event_type is EventType.RECONFIRM_GRANTED and e.seq > decision_event.seq
        ]
        if granted:
            actor = granted[-1].observed.get("actor", "unknown")
            return Authority(True, "RECONFIRMED", amount, f"held, then confirmed by {actor}")
        return Authority(False, "HELD", amount, "held pending re-confirmation")

    # --- settlement --------------------------------------------------------

    def open_order(self, request_id: str, gateway) -> OrderRef:
        """Create an order for the amount Custodian derived.

        Refuses unless settlement is authorised. The amount is the gate's own
        arithmetic over catalog prices — whatever the agent asserted, the payable
        figure is the one this system re-derived.
        """
        authority = self.settlement_authority(request_id)
        if not authority.allowed:
            raise PermissionError(f"{request_id} {authority}")

        order = gateway.create_order(
            amount_paise=authority.amount_paise, currency="INR", receipt=request_id,
            idempotency_key=f"{request_id}:order",
        )
        self.ledger.append(
            EventType.PAYMENT_INITIATED, request_id,
            observed={"gateway": gateway.name, **order.as_observed()},
            inferred={"authorised_by": authority.basis,
                      "approved_amount_paise": authority.amount_paise},
        )
        return order

    def capture(self, request_id: str, gateway, order: OrderRef) -> PaymentRef:
        """Take a payment, but only for the amount a decision approved.

        This is the last check before money is irreversible, and it is a
        different question from every check that came before. Those asked whether
        the *cart* was right. This asks whether the *payment in front of us* is
        the one that cart authorised.

        Three ways it can be wrong, all of which are refused rather than
        reconciled: the authority may have lapsed since the order was opened, the
        payer may have committed a different amount than the order asked for, and
        the payment may not correspond to this decision at all. A capture that
        quietly settles a mismatched amount would undo the whole verification
        chain at the last step.
        """
        authority = self.settlement_authority(request_id)
        if not authority.allowed:
            raise PermissionError(f"{request_id} {authority}")

        payment = gateway.payment_for(order)
        if payment is None:
            raise PaymentError(f"{request_id}: nobody has paid this order yet")

        if payment.amount_paise != authority.amount_paise:
            # Record the refusal. A mismatch is evidence, not a transient.
            self.ledger.append(
                EventType.PAYMENT_FAILED, request_id,
                observed={"gateway": gateway.name, **payment.as_observed()},
                inferred={"refused": "AMOUNT_MISMATCH",
                          "approved_amount_paise": authority.amount_paise,
                          "presented_amount_paise": payment.amount_paise},
            )
            raise AmountMismatch(
                f"{request_id}: payment presents {payment.amount_paise} paise, "
                f"the decision approved {authority.amount_paise}. Refusing to capture."
            )

        try:
            captured = gateway.capture(payment, idempotency_key=f"{request_id}:capture")
        except AlreadyCaptured:
            raise
        self.ledger.append(
            EventType.PAYMENT_SETTLED if captured.settled else EventType.PAYMENT_FAILED,
            request_id,
            observed={"gateway": gateway.name, **captured.as_observed()},
            inferred={"authorised_by": authority.basis},
        )
        return captured
