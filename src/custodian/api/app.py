"""The merchant endpoint.

Deliberately small. Every route is either evidence going in, a decision coming
out, or the record being read back — there is no route that lets a caller
influence how a decision is made.

Idempotency is required on the one route that can lead to money moving. An agent
that retries ``/v1/checkout/verify`` gets the decision it already has, not a
second one, because two decisions for one request would mean two orders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from custodian.api import view
from custodian.clock import utc_now
from custodian.gate.semantic import RecordedScorer
from custodian.gate.service import Custodian
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT
from custodian.ingest.snapshot import agent_feed, ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent.parser import resolve
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.replay import replay
from custodian.ledger.store import ArtifactStore
from custodian.ledger.verify import verify_chain
from custodian.money import format_inr
from custodian.payments.fake import FakeGateway
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.mandate import Mandate

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "data" / "catalog" / "kirana_export.csv"
MERCHANT = "kirana-blr-001"

#: One merchant, one mandate, modelled locally. Reserve Pay is not reachable
#: from a self-serve test account, and the README says so rather than implying
#: an integration that does not exist.
MANDATE = Mandate(
    mandate_id="mnd-demo", max_amount_paise=5_000_000, per_transaction_cap_paise=400_000,
    valid_from="2026-08-01T00:00:00+00:00", valid_until="2026-09-30T00:00:00+00:00",
    merchant_allowlist=(MERCHANT,),
)


def create_app(*, db_path: Path | None = None, gateway=None) -> FastAPI:
    app = FastAPI(
        title="Custodian",
        description="The purpose layer for agentic commerce. Re-derives what an agent bought "
                    "before money moves.",
        version="0.1.0",
    )

    taxonomy = default_taxonomy()
    tables = SubstitutionTables.from_taxonomy(taxonomy)
    if db_path is None:
        ledger, store = Ledger.in_memory(), ArtifactStore.in_memory()
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = Ledger.open(db_path)
        store = ArtifactStore.open(db_path.with_suffix(".artifacts.db"))

    state: dict[str, Any] = {
        "custodian": Custodian(ledger=ledger, store=store, tables=tables, scorer=RecordedScorer()),
        "gateway": gateway or FakeGateway(),
        "snapshot": None,
        "seen": {},  # idempotency key -> request_id
    }

    def snapshot():
        if state["snapshot"] is None:
            state["snapshot"], _ = ingest_csv(CATALOG, merchant_id=MERCHANT)
        return state["snapshot"]

    # --- catalog -----------------------------------------------------------

    @app.post("/v1/catalog/ingest", tags=["catalog"])
    def ingest() -> dict[str, Any]:
        """Normalise the merchant export into an agent-readable snapshot."""
        snap, report = ingest_csv(CATALOG, merchant_id=MERCHANT)
        state["snapshot"] = snap
        return {
            "snapshot_id": snap.snapshot_id, "digest": snap.digest(),
            "merchant_id": snap.merchant_id, "taken_at": snap.taken_at,
            "lexicon_version": snap.lexicon_version,
            "items_built": report.items_built, "rows_read": report.rows_read,
            "unplaced": [i.item_id for i in snap.items if not i.resolved],
            "resolutions": {k: len(report.of_kind(k)) for k in {i.kind for i in report.issues}},
        }

    @app.get("/v1/catalog/feed", tags=["catalog"])
    def feed() -> dict[str, Any]:
        """What a buying agent is given. Sanitised, and narrower than the snapshot."""
        snap = snapshot()
        return {"snapshot_id": snap.snapshot_id, "items": agent_feed(snap)}

    # --- checkout ----------------------------------------------------------

    @app.post("/v1/checkout/verify", tags=["checkout"])
    def verify(
        payload: dict = Body(...),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        """Re-derive a proposed purchase. The only route that decides anything."""
        if idempotency_key in state["seen"]:
            existing = state["seen"][idempotency_key]
            return _decision_response(state, existing, replayed=True)

        snap = snapshot()
        try:
            intent = resolve(payload["intent"], intent_id=f"{idempotency_key}-int",
                             taxonomy=taxonomy)
            lines = []
            for index, raw in enumerate(payload["cart"]):
                item = snap.find(raw["item_id"])
                lines.append(CartLine(
                    line_id=raw.get("line_id") or f"l{index + 1}",
                    item_id=raw["item_id"],
                    name_asserted=raw.get("name") or (item.name if item else raw["item_id"]),
                    quantity=raw.get("quantity", 1),
                    asserted_unit_price_paise=raw["asserted_unit_price_paise"],
                    satisfies_line_id=raw.get("satisfies_line_id"),
                ))
            cart = Cart(cart_id=f"{idempotency_key}-cart", merchant_id=MERCHANT,
                        lines=tuple(lines))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(422, f"malformed request: {exc}") from exc

        request_id = payload.get("request_id") or f"req-{idempotency_key}"
        state["custodian"].evaluate(
            request_id=request_id, intent=intent, cart=cart, snapshot=snap,
            mandate=MANDATE, thresholds=DEFAULT,
        )
        state["seen"][idempotency_key] = request_id
        return _decision_response(state, request_id)

    @app.post("/v1/checkout/confirm/{request_id}", tags=["checkout"])
    def confirm(request_id: str, actor: str = Query(...), note: str = Query("")) -> dict[str, Any]:
        """A human authorising a held purchase. Refused on a rejection."""
        try:
            state["custodian"].reconfirm(request_id, actor=actor, note=note)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _authority(state, request_id)

    @app.post("/v1/checkout/settle/{request_id}", tags=["checkout"])
    def settle(request_id: str) -> dict[str, Any]:
        """Move money, for the amount Custodian derived and only if permitted."""
        authority = state["custodian"].settlement_authority(request_id)
        if not authority.allowed:
            raise HTTPException(409, str(authority))

        gateway = state["gateway"]
        order = gateway.create_order(
            amount_paise=authority.amount_paise, currency="INR", receipt=request_id,
            idempotency_key=f"{request_id}:order",
        )
        state["custodian"].ledger.append(
            EventType.PAYMENT_INITIATED, request_id,
            observed={"gateway": gateway.name, **order.as_observed()},
        )
        return {
            "request_id": request_id, "basis": authority.basis,
            "amount_paise": authority.amount_paise,
            "amount": format_inr(authority.amount_paise),
            "order": order.as_observed(),
            "payment_url": getattr(gateway, "payment_link_for", lambda _o: None)(order),
        }

    # --- the record --------------------------------------------------------

    @app.get("/v1/ledger/verify", tags=["ledger"])
    def ledger_verify() -> dict[str, Any]:
        result = verify_chain(state["custodian"].ledger)
        return {"ok": result.ok, "events_checked": result.events_checked,
                "head": result.head, "breaks": [str(b) for b in result.breaks]}

    @app.get("/v1/ledger/{request_id}", tags=["ledger"])
    def ledger_read(request_id: str) -> dict[str, Any]:
        events = state["custodian"].ledger.read(request_id)
        if not events:
            raise HTTPException(404, f"no events for {request_id}")
        return {"request_id": request_id, "events": [
            {"seq": e.seq, "event_type": str(e.event_type), "ts": e.ts,
             "prev_hash": e.prev_hash, "hash": e.hash,
             "observed": e.observed, "inferred": e.inferred}
            for e in events
        ]}

    @app.post("/v1/replay/{request_id}", tags=["ledger"])
    def replay_request(request_id: str) -> dict[str, Any]:
        """Re-derive a recorded decision. No model is called."""
        result = replay(state["custodian"].ledger, state["custodian"].store, request_id,
                        tables=tables)
        if result.error and result.recorded is None:
            raise HTTPException(404, result.error)
        return {"request_id": request_id, "matched": result.matched,
                "summary": str(result), "differences": list(result.differences),
                "error": result.error}

    # --- the viewer --------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return view.index_page(state["custodian"].ledger)

    @app.get("/view/{request_id}", response_class=HTMLResponse, include_in_schema=False)
    def viewer(request_id: str) -> HTMLResponse:
        events = state["custodian"].ledger.read(request_id)
        if not events:
            return HTMLResponse(view.not_found(request_id), status_code=404)
        result = replay(state["custodian"].ledger, state["custodian"].store, request_id,
                        tables=tables)
        return HTMLResponse(view.decision_page(
            request_id=request_id, events=events, replay=result,
            authority=state["custodian"].settlement_authority(request_id),
            chain=verify_chain(state["custodian"].ledger),
        ))

    return app


def _decision_response(state, request_id: str, *, replayed: bool = False) -> dict[str, Any]:
    from custodian.ledger.chain import EventType as ET

    event = next(e for e in reversed(state["custodian"].ledger.read(request_id))
                 if e.event_type is ET.DECISION_MADE)
    decision = state["custodian"].store.get(event.inferred["decision_digest"])
    return {
        "request_id": request_id,
        "idempotent_replay": replayed,
        "outcome": decision["outcome"],
        "alignment_bp": decision["alignment_bp"],
        "confidence_bp": decision["confidence_bp"],
        "verified_total_paise": decision["verified_total_paise"],
        "verified_total": format_inr(decision["verified_total_paise"]),
        "asserted_total_paise": event.observed["asserted_total_paise"],
        "dimensions": decision["dimensions"],
        "bindings": decision["bindings"],
        "disposition_codes": decision["disposition_codes"],
        "escalated_line_ids": decision["escalated_line_ids"],
        "snapshot_digest": decision["snapshot_digest"],
        "thresholds_version": decision["thresholds_version"],
        "view": f"/view/{request_id}",
    }


def _authority(state, request_id: str) -> dict[str, Any]:
    authority = state["custodian"].settlement_authority(request_id)
    return {"request_id": request_id, "allowed": authority.allowed, "basis": authority.basis,
            "amount_paise": authority.amount_paise, "reason": authority.reason}


app = create_app()
