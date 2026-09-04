"""Day 5 checkpoint: catalog in, agent buys, real Razorpay order, ledger records.

Run:  set -a && . ./.env && set +a && .venv/bin/python scripts/settlement_demo.py

The gate itself is Days 6-8. What this proves today is the loop: messy catalog
normalised, intent parsed, cart built by an untrusted agent, the total
*re-derived server-side from the catalog*, a real test-mode order created for
that re-derived amount, and every step written to a hash-chained ledger.

The agent deliberately asserts a wrong price, so the one control that already
exists is visible: what gets charged is what Custodian derived, never what the
agent claimed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custodian.agent.buyer import NaiveBuyer
from custodian.clock import utc_now
from custodian.ingest.snapshot import agent_feed, ingest_csv
from custodian.intent.recorded import RecordedParser
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.verify import verify_chain
from custodian.money import format_inr, line_total
from custodian.payments.fake import FakeGateway
from custodian.schemas.cart import Cart, CartLine

GOAL = "ingredients for a thai curry, under Rs 2000"
MERCHANT = "kirana-blr-001"
REQUEST_ID = f"req-{utc_now().replace(':', '').replace('-', '')}"


def rule(title: str) -> None:
    print(f"\n{title}\n{'─' * 78}")


def main() -> int:
    ledger = Ledger.open("data/demo.db")

    rule("1. INGEST — messy merchant export in, agent-readable feed out")
    snapshot, report = ingest_csv("data/catalog/kirana_export.csv", merchant_id=MERCHANT)
    feed = agent_feed(snapshot)
    print(f"  {report}")
    print(f"  snapshot {snapshot.snapshot_id}  lexicon {snapshot.lexicon_version}")
    print(f"  {len(feed)} items exposed to the agent")
    ledger.append(EventType.SNAPSHOT_TAKEN, REQUEST_ID,
                  observed={"snapshot_id": snapshot.snapshot_id, "digest": snapshot.digest(),
                            "items": len(snapshot.items), "lexicon": snapshot.lexicon_version})

    rule("2. INTENT — natural language to structured constraints")
    parser = RecordedParser()
    parser.record(GOAL, {
        "goal": GOAL, "budget_paise": 200_000, "merchant_scope": [MERCHANT],
        "category_scope": None, "substitution_policy": "SAME_BASE",
        "requested_items": [
            {"raw_text": "coconut milk", "quantity": 2},
            {"raw_text": "thai red curry paste", "quantity": 1},
            {"raw_text": "lemongrass", "quantity": 1},
            {"raw_text": "fish sauce", "quantity": 1},
        ]})
    parsed = parser.parse(GOAL, intent_id=f"{REQUEST_ID}-int")
    intent = parsed.intent
    print(f'  "{intent.goal}"')
    print(f"  budget {format_inr(intent.budget_paise)}  policy {intent.substitution_policy}")
    for item in intent.requested_items:
        print(f"    {item.raw_text:22} x{item.quantity}  -> {item.base}/{item.form}")
    ledger.append(EventType.INTENT_RECEIVED, REQUEST_ID,
                  observed={"goal": intent.goal, "budget_paise": intent.budget_paise,
                            **parsed.as_observed()},
                  inferred={"items": len(intent.requested_items)})

    rule("3. AGENT — untrusted client builds a cart, and asserts a price")
    cart = NaiveBuyer().build_cart(intent, feed, cart_id=f"{REQUEST_ID}-crt",
                                   merchant_id=MERCHANT)
    # The agent understates one line. Nothing stops it: the cart is its claim.
    tampered = tuple(
        CartLine(**{**line.model_dump(), "asserted_unit_price_paise": 9_900})
        if index == 0 else line
        for index, line in enumerate(cart.lines)
    )
    cart = Cart(cart_id=cart.cart_id, merchant_id=cart.merchant_id, lines=tampered)
    for line in cart.lines:
        print(f"    {line.name_asserted[:34]:34} x{line.quantity} "
              f"@ {format_inr(line.asserted_unit_price_paise):>10} (asserted)")
    print(f"  agent claims total: {format_inr(cart.asserted_total_paise)}")

    rule("4. RE-DERIVATION — the catalog is the price, not the claim")
    verified = 0
    for line in cart.lines:
        item = snapshot.find(line.item_id)
        catalog_total = line_total(item.price_paise, line.quantity)
        verified += catalog_total
        flag = "" if item.price_paise == line.asserted_unit_price_paise else "  <- MISMATCH"
        print(f"    {line.item_id}  asserted {format_inr(line.asserted_unit_price_paise):>10}"
              f"   catalog {format_inr(item.price_paise):>10}{flag}")
    print(f"\n  agent asserted : {format_inr(cart.asserted_total_paise)}")
    print(f"  Custodian derived: {format_inr(verified)}   <- this is what may be charged")
    print(f"  within budget    : {verified <= intent.budget_paise}")
    ledger.append(EventType.DECISION_MADE, REQUEST_ID,
                  observed={"snapshot_digest": snapshot.digest(),
                            "asserted_total_paise": cart.asserted_total_paise},
                  inferred={"verified_total_paise": verified,
                            "within_budget": verified <= intent.budget_paise,
                            "note": "day-5 arithmetic only; the gate lands days 6-8"})

    rule("5. SETTLEMENT — a real Razorpay test-mode order")
    if os.environ.get("RAZORPAY_KEY_ID"):
        from custodian.payments.razorpay_client import RazorpayGateway
        gateway = RazorpayGateway()
    else:
        gateway = FakeGateway()
        print("  no credentials in env — falling back to FakeGateway")

    order = gateway.create_order(amount_paise=verified, currency="INR",
                                 receipt=REQUEST_ID, idempotency_key=f"{REQUEST_ID}:order")
    print(f"  gateway  {gateway.name}")
    print(f"  order    {order.order_id}")
    print(f"  amount   {format_inr(order.amount_paise)}  (the derived total, not the claim)")
    ledger.append(EventType.PAYMENT_INITIATED, REQUEST_ID,
                  observed={"gateway": gateway.name, **order.as_observed()})

    if hasattr(gateway, "payment_link_for"):
        try:
            url = gateway.payment_link_for(order)
            print(f"  payable  {url}")
            print("           (test card 5267 3181 8797 5449, any future expiry, any CVV)")
        except Exception as exc:
            print(f"  payable  link unavailable: {exc}")

    payment = gateway.payment_for(order)
    print(f"  payment  {payment or 'none yet — awaiting the payer'}")

    rule("6. LEDGER — what a dispute is resolved from")
    for event in ledger.read(REQUEST_ID):
        print(f"  {event.seq:>4}  {event.event_type:<18} {event.prev_hash[:8]}.. -> {event.hash[:8]}..")
    result = verify_chain(ledger)
    print(f"\n  {result}")
    ledger.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
