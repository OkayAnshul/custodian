"""The decision viewer.

One page, two jobs. It is the demo screen — the per-dimension breakdown a judge
needs to see to understand why an order was held — and it is the replay
credibility moment, since rendering it re-derives the decision from the ledger
and shows whether it reproduced.

Server-rendered, no build step, no framework. The page has to work from a clean
checkout on a laptop that has never run npm, and a decision viewer that needs a
toolchain to show a hash chain is not a serious artifact.
"""

from __future__ import annotations

import html
from typing import Any

from custodian import bp
from custodian.gate.reasons import ReasonCode, explain
from custodian.ledger.chain import EventType, LedgerEvent
from custodian.money import format_inr

_STYLE = """
:root {
  --bg:#fbfaf9; --panel:#fff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e6e2dd;
  --ok:#1f7a4d; --hold:#a86a12; --bad:#a8321f; --accent:#2b5c8a;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#141414; --panel:#1c1c1c; --ink:#ececec; --muted:#9a9a9a; --line:#2e2e2e;
          --ok:#4fbf85; --hold:#d9a441; --bad:#e0705c; --accent:#6fa8dc; }
}
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 ui-sans-serif,
       -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width:1080px; margin:0 auto; padding:32px 24px 72px }
h1 { font-size:22px; margin:0 0 4px; letter-spacing:-.01em }
h2 { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);
     margin:32px 0 10px; font-weight:600 }
.sub { color:var(--muted); margin:0 0 24px; font-size:14px }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:18px 20px }
.verdict { display:flex; align-items:baseline; gap:16px; flex-wrap:wrap }
.badge { font-size:26px; font-weight:700; letter-spacing:-.02em }
.APPROVE { color:var(--ok) } .HOLD { color:var(--hold) } .REJECT { color:var(--bad) }
.stat { color:var(--muted); font-size:13px }
.stat b { color:var(--ink); font-variant-numeric:tabular-nums; font-weight:600 }
table { width:100%; border-collapse:collapse; font-size:14px }
th { text-align:left; font-weight:600; color:var(--muted); font-size:12px;
     text-transform:uppercase; letter-spacing:.05em; padding:0 10px 8px 0 }
td { padding:9px 10px 9px 0; border-top:1px solid var(--line); vertical-align:top }
td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap }
.bar { height:6px; border-radius:3px; background:var(--line); overflow:hidden; min-width:90px }
.bar i { display:block; height:100% }
.PASS i { background:var(--ok) } .FAIL i { background:var(--bad) } .UNCERTAIN i { background:var(--hold) }
.tag { display:inline-block; font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
       border:1px solid var(--line); border-radius:4px; padding:1px 6px; margin:2px 4px 2px 0;
       color:var(--muted) }
code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px }
.why { color:var(--muted); font-size:13px; margin-top:2px }
.chain td { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px }
.ok { color:var(--ok) } .bad { color:var(--bad) } .warn { color:var(--hold) }
a { color:var(--accent) }
.note { border-left:3px solid var(--line); padding:2px 0 2px 14px; color:var(--muted);
        font-size:13px; margin:12px 0 }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:14px }
@media (max-width:760px){ .grid{grid-template-columns:1fr} }
.scroll { overflow-x:auto }
"""


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><div class='wrap'>{body}</div></body></html>"
    )


def _e(value: Any) -> str:
    return html.escape(str(value))


def not_found(request_id: str) -> str:
    return _page("Not found", f"<h1>No such request</h1>"
                              f"<p class='sub'>Nothing recorded for <code>{_e(request_id)}</code>.</p>"
                              f"<p><a href='/'>All decisions</a></p>")


def index_page(ledger) -> str:
    rows = []
    for event in ledger.scan():
        if event.event_type is not EventType.DECISION_MADE:
            continue
        outcome = event.inferred["outcome"]
        rows.append(
            f"<tr><td><a href='/view/{_e(event.request_id)}'><code>{_e(event.request_id)}</code></a></td>"
            f"<td class='{_e(outcome)}'><b>{_e(outcome)}</b></td>"
            f"<td class='num'>{bp.to_str(event.inferred['alignment_bp'])}</td>"
            f"<td class='num'>{bp.to_str(event.inferred['confidence_bp'])}</td>"
            f"<td class='num'>{_e(format_inr(event.inferred['verified_total_paise']))}</td>"
            f"<td class='mono' style='color:var(--muted)'>{_e(event.ts)}</td></tr>"
        )
    table = (
        "<table><tr><th>request</th><th>outcome</th><th style='text-align:right'>alignment</th>"
        "<th style='text-align:right'>confidence</th><th style='text-align:right'>verified total</th>"
        f"<th>recorded</th></tr>{''.join(reversed(rows))}</table>"
        if rows else "<p class='sub'>No decisions recorded yet.</p>"
    )
    return _page("Custodian", (
        "<h1>Custodian</h1>"
        "<p class='sub'>An AI buyer can be authorised to spend. This checks whether it bought "
        "what the human actually asked for.</p>"
        f"<div class='panel scroll'>{table}</div>"
    ))


def decision_page(*, request_id: str, events: list[LedgerEvent], replay, authority, chain) -> str:
    decision_event = next(
        (e for e in reversed(events) if e.event_type is EventType.DECISION_MADE), None
    )
    if decision_event is None or replay.recorded is None:
        return not_found(request_id)

    decision = replay.recorded
    asserted = decision_event.observed.get("asserted_total_paise", 0)

    head = (
        f"<h1>Decision <code>{_e(request_id)}</code></h1>"
        f"<p class='sub'>Re-derived from the ledger when you loaded this page.</p>"
        f"<div class='panel'><div class='verdict'>"
        f"<span class='badge {_e(decision.outcome)}'>{_e(decision.outcome)}</span>"
        f"<span class='stat'>alignment <b>{bp.to_str(decision.alignment_bp)}</b></span>"
        f"<span class='stat'>confidence <b>{bp.to_str(decision.confidence_bp)}</b></span>"
        f"<span class='stat'>agent asserted <b>{_e(format_inr(asserted))}</b></span>"
        f"<span class='stat'>Custodian derived <b>{_e(format_inr(decision.verified_total_paise))}</b></span>"
        f"</div><p class='why'>{_e(decision.reason_text)}</p></div>"
    )

    dimension_rows = "".join(
        f"<tr><td>{_e(d.dimension)}</td>"
        f"<td><div class='bar {_e(d.status)}'><i style='width:{d.score_bp / 100:.0f}%'></i></div></td>"
        f"<td class='num'>{bp.to_str(d.score_bp)}</td>"
        f"<td class='{'ok' if str(d.status) == 'PASS' else ('bad' if str(d.status) == 'FAIL' else 'warn')}'>"
        f"{_e(d.status)}</td>"
        f"<td>{''.join(f'<span class=tag>{_e(c)}</span>' for c in d.reason_codes)}"
        f"<div class='why'>{_e(d.reason_text)}</div></td></tr>"
        for d in decision.dimensions
    )
    dimensions = (
        "<h2>Why — every dimension scored separately</h2><div class='panel scroll'><table>"
        "<tr><th>dimension</th><th></th><th style='text-align:right'>score</th><th>status</th>"
        f"<th>reason</th></tr>{dimension_rows}</table>"
        + (
            "<div class='note'>"
            + "".join(f"<span class='tag'>{_e(c)}</span>" for c in decision.disposition_codes)
            + " ".join(explain(ReasonCode(c)) for c in decision.disposition_codes)
            + "</div>" if decision.disposition_codes else ""
        )
        + "</div>"
    )

    binding_rows = "".join(
        f"<tr><td><code>{_e(b.cart_line_id)}</code></td>"
        f"<td><code>{_e(b.requested_line_id or '—')}</code></td>"
        f"<td>{_e(b.kind)}</td><td class='num'>{bp.to_str(b.score_bp)}</td>"
        f"<td>{''.join(f'<span class=tag>{_e(c)}</span>' for c in b.reason_codes)}</td></tr>"
        for b in decision.bindings
    )
    bindings = (
        "<h2>What each cart line answers</h2><div class='panel scroll'><table>"
        "<tr><th>cart line</th><th>requested</th><th>kind</th>"
        f"<th style='text-align:right'>fidelity</th><th></th></tr>{binding_rows}</table>"
        "<div class='note'>A line bound to nothing is scope creep: it may be correctly priced, "
        "in stock and inside budget, and still not be what anyone asked for.</div></div>"
    )

    chain_rows = "".join(
        f"<tr><td>{e.seq}</td><td>{_e(e.event_type)}</td>"
        f"<td>{_e(e.prev_hash[:12])}…</td><td>{_e(e.hash[:12])}…</td>"
        f"<td style='color:var(--muted)'>{_e(e.ts)}</td></tr>"
        for e in events
    )
    integrity = (
        f"<span class='ok'>chain intact — {chain.events_checked} events</span>"
        if chain.ok else f"<span class='bad'>CHAIN BROKEN — {_e(str(chain))}</span>"
    )
    replay_line = (
        f"<span class='ok'>reproduces exactly</span>" if replay.matched
        else f"<span class='bad'>diverged — {_e('; '.join(replay.differences) or replay.error)}</span>"
    )

    record = (
        "<h2>The record</h2><div class='grid'>"
        f"<div class='panel'><p class='stat'>Replay<br><b>{replay_line}</b></p>"
        f"<p class='stat'>Integrity<br><b>{integrity}</b></p>"
        f"<p class='stat'>Settlement<br><b class='{'ok' if authority.allowed else 'warn'}'>"
        f"{_e(str(authority))}</b></p></div>"
        f"<div class='panel'><p class='stat'>Catalog snapshot<br>"
        f"<code>{_e(decision.snapshot_digest[:32])}…</code></p>"
        f"<p class='stat'>Thresholds<br><code>{_e(decision.thresholds_version)}</code> "
        f"<code>{_e(decision.thresholds_digest[:16])}…</code></p>"
        f"<p class='stat'>Escalated to a model<br><b>"
        f"{_e(', '.join(decision.escalated_line_ids) or 'nothing — decided by arithmetic')}"
        f"</b></p></div></div>"
        f"<div class='panel scroll' style='margin-top:14px'><table class='chain'>"
        "<tr><th>seq</th><th>event</th><th>prev</th><th>hash</th><th>recorded</th></tr>"
        f"{chain_rows}</table></div>"
    )

    return _page(f"Custodian — {request_id}",
                 head + dimensions + bindings + record + "<p style='margin-top:28px'><a href='/'>"
                 "← all decisions</a></p>")


def checkout_page(*, request_id: str, key_id: str, order_id: str, amount_paise: int,
                  description: str) -> str:
    """The hosted page a payer completes an order on.

    This is the one part of the loop no API call can perform: a person has to
    put a card in. The page hands the payment back to
    ``POST /v1/checkout/callback/{request_id}``, where the signature is checked
    before anything is captured — the browser is an untrusted client too.

    Test card 4111 1111 1111 1111, any future expiry, any CVV.
    """
    return _page(f"Pay — {request_id}", (
        f"<h1>Custodian</h1>"
        f"<p class='sub'>Order <code>{_e(order_id)}</code> for request "
        f"<code>{_e(request_id)}</code>.</p>"
        f"<div class='panel'>"
        f"<p class='stat'>Amount<br><b style='font-size:22px'>{_e(format_inr(amount_paise))}</b></p>"
        f"<p class='why'>{_e(description)}</p>"
        f"<p class='why'>This is the amount Custodian derived from the catalog, "
        f"not the amount the agent asserted.</p>"
        f"<p id='status' class='stat'></p>"
        f"<p><button id='pay' style='font:inherit;padding:9px 18px;border-radius:8px;"
        f"border:1px solid var(--line);background:var(--accent);color:#fff;cursor:pointer'>"
        f"Pay {_e(format_inr(amount_paise))}</button></p>"
        f"<p class='why'>Test mode. Card 4111 1111 1111 1111, any future expiry, any CVV.</p>"
        f"</div>"
        f"<script src='https://checkout.razorpay.com/v1/checkout.js'></script>"
        f"<script>\n"
        f"const status = document.getElementById('status');\n"
        f"document.getElementById('pay').onclick = function () {{\n"
        f"  const rzp = new Razorpay({{\n"
        f"    key: {key_id!r},\n"
        f"    amount: {amount_paise},\n"
        f"    currency: 'INR',\n"
        f"    name: 'Custodian',\n"
        f"    description: {description!r},\n"
        f"    order_id: {order_id!r},\n"
        f"    theme: {{ color: '#2b5c8a' }},\n"
        f"    handler: function (response) {{\n"
        f"      status.textContent = 'verifying signature\\u2026';\n"
        f"      fetch('/v1/checkout/callback/{request_id}', {{\n"
        f"        method: 'POST',\n"
        f"        headers: {{ 'Content-Type': 'application/json' }},\n"
        f"        body: JSON.stringify(response)\n"
        f"      }}).then(r => r.json().then(b => ({{ ok: r.ok, body: b }})))\n"
        f"        .then(({{ ok, body }}) => {{\n"
        f"          status.innerHTML = ok\n"
        f"            ? '<b class=ok>settled \\u2014 ' + body.payment.payment_id +\n"
        f"              '</b><br><a href=\"/view/{request_id}\">see the decision</a>'\n"
        f"            : '<b class=bad>' + (body.detail || 'refused') + '</b>';\n"
        f"        }});\n"
        f"    }},\n"
        f"    modal: {{ ondismiss: function () {{ status.textContent = 'cancelled'; }} }}\n"
        f"  }});\n"
        f"  rzp.on('payment.failed', function (r) {{\n"
        f"    status.innerHTML = '<b class=bad>declined: ' + r.error.description + '</b>';\n"
        f"  }});\n"
        f"  rzp.open();\n"
        f"}};\n"
        f"</script>"
    ))
