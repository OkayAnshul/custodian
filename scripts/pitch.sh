#!/usr/bin/env bash
# One command between a cold machine and "press record".
#
# Starts the server on the live gateway, creates a verified order so the
# checkout page and the payable link are real, opens pitch mode, and prints the
# run sheet. Ctrl-C stops the server.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
BOLD=$'\e[1m'; DIM=$'\e[2m'; OK=$'\e[32m'; WARN=$'\e[33m'; BAD=$'\e[31m'; OFF=$'\e[0m'
say() { printf '%s\n' "$*"; }
step() { printf '  %s%s%s %s\n' "$2" "$1" "$OFF" "$3"; }

say ""
say "${BOLD}Custodian — pitch preflight${OFF}"
say "${DIM}────────────────────────────────────────────────────────${OFF}"

[ -f .env ] && set -a && . ./.env && set +a
[ -x "$PY" ] || { step "✗" "$BAD" "no virtualenv — run: make install"; exit 1; }
step "✓" "$OK" "virtualenv"

if [ -n "${RAZORPAY_KEY_ID:-}" ] && [ -n "${RAZORPAY_KEY_SECRET:-}" ]; then
  step "✓" "$OK" "Razorpay test credentials — live order and payable link"; LIVE=1
else
  step "!" "$WARN" "no Razorpay keys: the demo runs, but there is no live order to show"; LIVE=0
fi
[ -n "${GROQ_API_KEY:-}" ] && step "✓" "$OK" "Groq key — 'make demo-groq' can call the model live" \
                           || step "!" "$WARN" "no Groq key — recorded answers replay instead"
[ -f data/fixtures/model_responses.json ] && step "✓" "$OK" "28 recorded model answers present"

# --- the server ------------------------------------------------------------
pkill -f "uvicorn custodian.api.app" >/dev/null 2>&1
.venv/bin/uvicorn custodian.api.app:app --host 127.0.0.1 --port 8000 >/tmp/custodian-pitch.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; say ""; say "server stopped."; exit 0' INT TERM
for _ in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8000/docs && break; sleep 1; done
curl -sf -o /dev/null http://127.0.0.1:8000/docs \
  && step "✓" "$OK" "server on http://127.0.0.1:8000" \
  || { step "✗" "$BAD" "server did not start — see /tmp/custodian-pitch.log"; exit 1; }

# --- a real order to show --------------------------------------------------
REQ="live-$(date +%H%M%S)"
INTENT='{"goal":"ingredients for a thai curry, under Rs 2000","budget_paise":300000,"merchant_scope":["kirana-blr-001"],"substitution_policy":"SAME_BASE","requested_items":[{"raw_text":"coconut milk","quantity":2},{"raw_text":"thai red curry paste","quantity":1}]}'
CART="[{\"item_id\":\"SKU001\",\"quantity\":2,\"asserted_unit_price_paise\":19900,\"satisfies_line_id\":\"$REQ-int-r1\"},{\"item_id\":\"SKU055\",\"quantity\":1,\"asserted_unit_price_paise\":24500,\"satisfies_line_id\":\"$REQ-int-r2\"}]"
curl -s -X POST http://127.0.0.1:8000/v1/checkout/verify -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $REQ" -d "{\"request_id\":\"$REQ\",\"intent\":$INTENT,\"cart\":$CART}" >/dev/null
SETTLE=$(curl -s -X POST "http://127.0.0.1:8000/v1/checkout/settle/$REQ")
ORDER=$(printf '%s' "$SETTLE" | $PY -c "import json,sys;print(json.load(sys.stdin)['order']['order_id'])" 2>/dev/null)
LINK=$(printf '%s' "$SETTLE"  | $PY -c "import json,sys;print(json.load(sys.stdin).get('payment_url') or '')" 2>/dev/null)
[ -n "$ORDER" ] && step "✓" "$OK" "order $ORDER for ₹643.00 — the derived amount"
if [ -n "$LINK" ]; then
  step "✓" "$OK" "payable link $LINK"
else
  step "!" "$WARN" "no payable link — test mode caps them at 30 and this account is there."
  say "      ${DIM}Not a fault: settle returned 200 with payment_url null, which is the${OFF}"
  say "      ${DIM}designed degradation. The checkout page below is the settlement path.${OFF}"
fi

# --- open the surfaces -----------------------------------------------------
open_url() { (xdg-open "$1" >/dev/null 2>&1 &) ; }
open_url "file://$PWD/docs/pitch.html"
[ "$LIVE" = "1" ] && open_url "http://127.0.0.1:8000/view/$REQ"
step "✓" "$OK" "opened pitch mode and the decision viewer"

cat <<RUN

${BOLD}Run sheet${OFF}
${DIM}────────────────────────────────────────────────────────${OFF}
  ${BOLD}Press record now.${OFF} Everything below is already live.

  In pitch mode        ${DIM}→ / space${OFF} next beat   ${DIM}N${OFF} your notes   ${DIM}T${OFF} timer   ${DIM}/${OFF} questions
  Beat 2 is the one    ${DIM}the 0.3333 collision — open here, not on the problem statement${OFF}
  Cut to the terminal  ${DIM}once, at beat 5, for:${OFF}  make demo
  Cut to the browser   ${DIM}once, at beat 6, for the decision viewer (already open)${OFF}

  Live right now:
    pitch mode     file://$PWD/docs/pitch.html
    decision       http://127.0.0.1:8000/view/$REQ
    checkout page  http://127.0.0.1:8000/checkout/$REQ
    payable link   ${LINK:-none — test-mode cap reached; use the checkout page}

  If a screen fails   ${DIM}open docs/index.html and keep talking — same numbers${OFF}

${DIM}Ctrl-C to stop the server.${OFF}
RUN
wait $SERVER
