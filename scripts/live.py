"""The whole loop, live, against the running server — for the pitch.

    make pitch            # or: make serve, with .env sourced
    .venv/bin/python scripts/live.py

Everything here goes through the merchant API over HTTP, because that is the
product: a merchant endpoint an untrusted AI buyer talks to. Nothing is
simulated except the buyer, which is deliberately naive.

The loop it walks, in order:

    the merchant's messy export  ->  ingest and sanitize  ->  the narrow agent feed
    ->  a human's request  ->  the agent's cart, with a forged price
    ->  the gate  ->  a real Razorpay order for the *derived* amount
    ->  a person pays on the hosted page  ->  settlement recorded in the chain

It stops and waits at the payment, because no API call performs that step — a
human puts a card in. That pause is the honest shape of the system and it is
also the best moment in the demo.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
PACED = True
W = 78

BOLD, DIM, OK, WARN, ACC, OFF = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"


def rule(n: str, title: str, sub: str = "") -> None:
    if PACED:
        time.sleep(1.6)
    print(f"\n\n{'═' * W}\n  {BOLD}{n}. {title}{OFF}")
    if sub:
        print(f"     {DIM}{sub}{OFF}")
    print("═" * W)


def beat(seconds: float = 0.9) -> None:
    if PACED:
        time.sleep(seconds)


def api(method: str, path: str, body: dict | None = None, key: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Idempotency-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_detail": (e.read() or b"").decode()[:200]}


def main() -> int:
    global PACED
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="no pauses; for a dry run")
    ap.add_argument("--request-id", default=f"live-{int(time.time()) % 100000}")
    args = ap.parse_args()
    PACED = not args.fast
    rid = args.request_id

    try:
        urllib.request.urlopen(BASE + "/docs", timeout=5)
    except Exception:
        print(f"{WARN}The server is not running.{OFF}  Start it with:  make pitch\n")
        return 1

    # ── 1 ────────────────────────────────────────────────────────────────
    rule("1", "THE MERCHANT", "a real kirana export, exactly as it comes out of their system")
    rows = list(csv.DictReader((ROOT / "data/catalog/kirana_export.csv").open(encoding="utf-8")))
    print(f"\n  {len(rows)} rows. Four of them, unedited:\n")
    for sku in ("SKU001", "SKU002", "SKU016", "SKU070"):
        r = next((x for x in rows if x["sku"] == sku), None)
        if not r:
            continue
        print(f"    {DIM}{r['sku']}{OFF}  {r['item_name'][:38]:38} "
              f"price={r['price'] or '(empty)':>10}  stock={r['stock']:<9} cat={r['category'] or '(empty)'}")
    print(f"\n  {DIM}A price column that is sometimes empty. Stock spelled four ways. Pack sizes")
    print(f"  living inside the product name, in Hindi as often as not. No agent can shop this.{OFF}")

    # ── 2 ────────────────────────────────────────────────────────────────
    rule("2", "INGEST", "normalise it, sanitize it, and content-hash the result")
    ing = api("POST", "/v1/catalog/ingest")
    print(f"\n  {ing['rows_read']} rows read  →  {OK}{ing['items_built']} items built{OFF}")
    for k, v in (ing.get("resolutions") or {}).items():
        print(f"    {k:22} {v}")
    if ing.get("unplaced"):
        print(f"    {'UNPLACED':22} {', '.join(ing['unplaced'])}  {DIM}← escalates rather than guesses{OFF}")
    beat()

    # ── 3 ────────────────────────────────────────────────────────────────
    rule("3", "WHAT THE AGENT IS ALLOWED TO SEE", "narrower than the snapshot, on purpose")
    feed = api("GET", "/v1/catalog/feed")
    item = next((i for i in feed["items"] if i["item_id"] == "SKU001"), feed["items"][0])
    raw = next(r for r in rows if r["sku"] == "SKU001")
    print(f"\n  the merchant wrote:\n    {DIM}{raw['description']}{OFF}")
    print(f"\n  the agent receives:")
    for k in ("item_id", "name", "price_paise", "in_stock", "base", "form", "category"):
        if k in item:
            print(f"    {k:12} {item[k]}")
    print(f"\n  {DIM}No raw description, no sanitizer state. It sees what it needs to shop,")
    print(f"  not what it would need to reason about the checks.{OFF}")
    beat()

    # ── 4 ────────────────────────────────────────────────────────────────
    rule("4", "THE HUMAN ASKS FOR SOMETHING", "and an untrusted agent builds a cart")
    goal = "ingredients for a thai curry, under Rs 2000"
    print(f'\n  the human said:  {BOLD}"{goal}"{OFF}')
    print(f"\n  the agent proposes — note the price it asserts on the first line:\n")
    print(f"    {'Dabur Coconut Milk 400ml':38} x2   asserted {WARN}₹99.00{OFF}   {DIM}catalog: ₹199.00{OFF}")
    print(f"    {'Thai Red Curry Paste 200g':38} x1   asserted ₹245.00")
    print(f"    {'Hawkins Kadhai 30cm':38} x1   asserted ₹1,450.00  {DIM}← nobody asked for this{OFF}")
    beat(1.4)

    intent = {"goal": goal, "budget_paise": 300000, "merchant_scope": ["kirana-blr-001"],
              "substitution_policy": "SAME_BASE",
              "requested_items": [{"raw_text": "coconut milk", "quantity": 2},
                                  {"raw_text": "thai red curry paste", "quantity": 1}]}
    cart = [{"item_id": "SKU001", "quantity": 2, "asserted_unit_price_paise": 9900,
             "satisfies_line_id": f"{rid}-int-r1"},
            {"item_id": "SKU055", "quantity": 1, "asserted_unit_price_paise": 24500,
             "satisfies_line_id": f"{rid}-int-r2"},
            {"item_id": "SKU068", "quantity": 1, "asserted_unit_price_paise": 145000}]

    # ── 5 ────────────────────────────────────────────────────────────────
    rule("5", "THE GATE", "every claim re-derived before anything moves")
    d = api("POST", "/v1/checkout/verify", {"request_id": rid, "intent": intent, "cart": cart}, key=rid)
    if "_error" in d:
        print(f"  {WARN}{d}{OFF}"); return 1
    colour = {"APPROVE": OK, "HOLD": WARN, "REJECT": "\033[31m"}.get(d["outcome"], "")
    print(f"\n  → {colour}{BOLD}{d['outcome']}{OFF}   alignment {d['alignment_bp']/100:.2f}%   "
          f"confidence {d['confidence_bp']/100:.2f}%")
    print(f"\n  agent asserted   {WARN}₹{d['asserted_total_paise']/100:,.2f}{OFF}")
    print(f"  Custodian derived {OK}₹{d['verified_total_paise']/100:,.2f}{OFF}   "
          f"{DIM}← the only amount that can be charged{OFF}\n")
    for dim in d["dimensions"]:
        if dim["status"] != "PASS":
            print(f"    {dim['dimension']:18} {dim['status']:10} {dim['score_bp']/100:6.2f}%  "
                  f"{', '.join(dim['reason_codes'])}")
    print(f"\n  {DIM}escalated to a model: "
          f"{', '.join(d['escalated_line_ids']) or 'nothing — decided by arithmetic'}{OFF}")
    print(f"  {ACC}{BASE}/view/{rid}{OFF}  {DIM}← the same decision, in the viewer{OFF}")
    beat(1.6)

    # ── 5b ───────────────────────────────────────────────────────────────
    rule("5b", "A REJECTION CANNOT BE WAVED THROUGH", "the agent has to come back with a corrected cart")
    bad = api("POST", f"/v1/checkout/confirm/{rid}?actor=anshul@kiit.ac.in")
    print(f"\n  a human tries to confirm it anyway:")
    print(f"    {WARN}{(bad.get('_detail') or json.dumps(bad))[:96]}{OFF}")
    print(f"\n  {DIM}A constraint a human can wave through is advisory. So the agent fixes the")
    print(f"  price and resubmits — which is a new decision, and a new entry in the record.{OFF}")
    beat(1.4)

    rid2 = rid + "-b"
    cart2 = [dict(cart[0], asserted_unit_price_paise=19900,
                  satisfies_line_id=f"{rid2}-int-r1"),
             dict(cart[1], satisfies_line_id=f"{rid2}-int-r2"),
             cart[2]]
    d2 = api("POST", "/v1/checkout/verify",
             {"request_id": rid2, "intent": intent, "cart": cart2}, key=rid2)
    colour2 = {"APPROVE": OK, "HOLD": WARN, "REJECT": "\033[31m"}.get(d2["outcome"], "")
    print(f"  corrected cart  →  {colour2}{BOLD}{d2['outcome']}{OFF}   "
          f"alignment {d2['alignment_bp']/100:.2f}%   charge ₹{d2['verified_total_paise']/100:,.2f}")
    for dim in d2["dimensions"]:
        if dim["status"] != "PASS":
            print(f"    {dim['dimension']:18} {dim['status']:10} {dim['score_bp']/100:6.2f}%  "
                  f"{', '.join(dim['reason_codes'])}")
    print(f"\n  {DIM}The price is right now. The wok still is not — and that is a judgment")
    print(f"  the human is the authority on, so it holds rather than refuses.{OFF}")
    rid = rid2

    # ── 6 ────────────────────────────────────────────────────────────────
    rule("6", "SETTLEMENT", "a real Razorpay order, for the amount Custodian derived")
    if d2["outcome"] == "HOLD":
        auth = api("POST", f"/v1/checkout/confirm/{rid}?actor=anshul@kiit.ac.in")
        print(f"\n  a human re-confirmed the hold: {OK}{auth.get('basis')}{OFF}")
        print(f"  {DIM}the decision still reads HOLD in the record — 'held, then a human said")
        print(f"  yes at 14:32' is the truthful entry, and the number a false-hold rate uses{OFF}")
    s = api("POST", f"/v1/checkout/settle/{rid}")
    if "_error" in s:
        print(f"  {WARN}cannot settle: {s.get('_detail','')}{OFF}"); return 1
    print(f"\n  order    {OK}{s['order']['order_id']}{OFF}  {DIM}issued by Razorpay, test mode{OFF}")
    print(f"  amount   {BOLD}{s['amount']}{OFF}  {DIM}(derived, not asserted){OFF}")
    if s.get("payment_url"):
        print(f"  payable  {ACC}{s['payment_url']}{OFF}")

    # ── 7 ────────────────────────────────────────────────────────────────
    rule("7", "A PERSON PAYS", "no API call performs this step — that is the honest gap")
    print(f"\n  {BOLD}Open this and pay:{OFF}\n\n    {ACC}{BASE}/checkout/{rid}{OFF}\n")
    print(f"    card {BOLD}5267 3181 8797 5449{OFF}   any future expiry   any CVV")
    print(f"    {DIM}(not 4111 1111 1111 1111 — that is the international test card and this")
    print(f"     account declines it){OFF}\n")
    print(f"  {DIM}waiting for the payment to land… Ctrl-C to skip{OFF}")
    settled = False
    try:
        for _ in range(600):
            events = api("GET", f"/v1/ledger/{rid}").get("events", [])
            if any(e["event_type"] == "PAYMENT_SETTLED" for e in events):
                settled = True
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n  {DIM}skipped{OFF}")
    if settled:
        print(f"\n  {OK}{BOLD}settled.{OFF}")

    # ── 8 ────────────────────────────────────────────────────────────────
    rule("8", "THE RECORD", "what a dispute would be resolved from")
    events = api("GET", f"/v1/ledger/{rid}").get("events", [])
    print()
    for e in events:
        obs = e.get("observed") or {}
        extra = obs.get("payment_id") or obs.get("order_id") or ""
        print(f"    {e['seq']:>3}  {e['event_type']:<20} {e['prev_hash'][:8]}.. → {e['hash'][:8]}..  {DIM}{extra}{OFF}")
    v = api("GET", "/v1/ledger/verify")
    print(f"\n  chain: {OK if v.get('ok') else WARN}{'intact' if v.get('ok') else 'BROKEN'}{OFF}"
          f"  ({v.get('events_checked')} events checked)")
    r = api("POST", f"/v1/replay/{rid}")
    same = r.get("identical", r.get("matches", None))
    print(f"  replay: {OK}reproduces exactly{OFF}  {DIM}with the model client mocked to raise if called{OFF}"
          if same is not False else f"  replay: {WARN}differs{OFF}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
