"""The merchant endpoint, end to end."""

import pytest
from fastapi.testclient import TestClient

from custodian.api.app import create_app

INTENT = {
    "goal": "ingredients for a thai curry, under Rs 2000", "budget_paise": 300_000,
    "merchant_scope": ["kirana-blr-001"], "substitution_policy": "SAME_BASE",
    "requested_items": [{"raw_text": "coconut milk", "quantity": 2},
                        {"raw_text": "thai red curry paste", "quantity": 1}],
}
CLEAN_CART = [
    {"item_id": "SKU001", "quantity": 2, "asserted_unit_price_paise": 19_900,
     "satisfies_line_id": "k-int-r1"},
    {"item_id": "SKU055", "quantity": 1, "asserted_unit_price_paise": 24_500,
     "satisfies_line_id": "k-int-r2"},
]
WOK = {"item_id": "SKU068", "quantity": 1, "asserted_unit_price_paise": 145_000}


@pytest.fixture
def client():
    return TestClient(create_app())


def verify(client, cart, *, key="k1", request_id="req-1", intent=INTENT):
    return client.post("/v1/checkout/verify",
                       json={"request_id": request_id, "intent": intent, "cart": cart},
                       headers={"Idempotency-Key": key})


def test_ingest_reports_what_it_had_to_resolve(client):
    body = client.post("/v1/catalog/ingest").json()
    assert body["rows_read"] == 70 and body["items_built"] == 70
    assert body["unplaced"] == ["SKU070"]
    assert body["resolutions"]["PRICE_FROM_MRP"] == 5


def test_the_feed_is_narrower_than_the_snapshot(client):
    entry = client.get("/v1/catalog/feed").json()["items"][0]
    assert "raw_description" not in entry and "sanitization" not in entry


def test_a_clean_order_approves(client):
    body = verify(client, CLEAN_CART).json()
    assert body["outcome"] == "APPROVE"
    assert body["verified_total_paise"] == 64_300


def test_the_charged_amount_is_derived_not_asserted(client):
    forged = [dict(CLEAN_CART[0], asserted_unit_price_paise=9_900), CLEAN_CART[1]]
    body = verify(client, forged).json()
    assert body["outcome"] == "REJECT"
    assert body["asserted_total_paise"] == 44_300
    assert body["verified_total_paise"] == 64_300


def test_an_unrequested_item_holds(client):
    body = verify(client, CLEAN_CART + [WOK]).json()
    assert body["outcome"] == "HOLD"
    assert any(d["dimension"] == "SCOPE_CREEP" and d["status"] == "FAIL"
               for d in body["dimensions"])


def test_a_retried_request_returns_one_decision_not_two(client):
    """Two decisions for one request would mean two orders."""
    first = verify(client, CLEAN_CART, key="same").json()
    second = verify(client, CLEAN_CART, key="same").json()
    assert second["idempotent_replay"] and not first["idempotent_replay"]
    assert first["outcome"] == second["outcome"]


def test_the_idempotency_header_is_required(client):
    response = client.post("/v1/checkout/verify", json={"intent": INTENT, "cart": CLEAN_CART})
    assert response.status_code == 422


def test_a_malformed_request_is_refused_not_guessed_at(client):
    response = client.post("/v1/checkout/verify",
                           json={"intent": INTENT, "cart": [{"item_id": "SKU001"}]},
                           headers={"Idempotency-Key": "bad"})
    assert response.status_code == 422


# --- settlement ------------------------------------------------------------

def test_a_held_order_cannot_settle_until_confirmed(client):
    verify(client, CLEAN_CART + [WOK])
    assert client.post("/v1/checkout/settle/req-1").status_code == 409

    confirmed = client.post("/v1/checkout/confirm/req-1?actor=anshul@kiit.ac.in").json()
    assert confirmed["basis"] == "RECONFIRMED" and confirmed["allowed"]

    settled = client.post("/v1/checkout/settle/req-1").json()
    assert settled["basis"] == "RECONFIRMED"
    assert settled["amount_paise"] == 64_300 + 145_000


def test_a_rejected_order_cannot_be_confirmed_past(client):
    forged = [dict(CLEAN_CART[0], asserted_unit_price_paise=1), CLEAN_CART[1]]
    verify(client, forged)
    assert client.post("/v1/checkout/confirm/req-1?actor=anshul@kiit.ac.in").status_code == 409
    assert client.post("/v1/checkout/settle/req-1").status_code == 409


def test_settlement_orders_the_derived_amount(client):
    forged = [dict(CLEAN_CART[0], asserted_unit_price_paise=19_900), CLEAN_CART[1]]
    verify(client, forged)
    settled = client.post("/v1/checkout/settle/req-1").json()
    assert settled["order"]["amount_paise"] == 64_300


# --- the record ------------------------------------------------------------

def test_the_ledger_is_readable_per_request(client):
    verify(client, CLEAN_CART)
    events = client.get("/v1/ledger/req-1").json()["events"]
    assert [e["event_type"] for e in events] == \
           ["INTENT_RECEIVED", "SNAPSHOT_TAKEN", "DECISION_MADE"]
    assert all("observed" in e and "inferred" in e for e in events)


def test_the_chain_verifies(client):
    verify(client, CLEAN_CART)
    body = client.get("/v1/ledger/verify").json()
    assert body["ok"] and body["events_checked"] == 3


def test_a_decision_replays_over_http(client):
    verify(client, CLEAN_CART)
    body = client.post("/v1/replay/req-1").json()
    assert body["matched"] and "reproduces exactly" in body["summary"]


def test_reading_something_that_never_happened_is_a_404(client):
    assert client.get("/v1/ledger/nope").status_code == 404
    assert client.post("/v1/replay/nope").status_code == 404


# --- the viewer ------------------------------------------------------------

def test_the_viewer_renders_the_breakdown_a_judge_needs(client):
    verify(client, CLEAN_CART + [WOK])
    page = client.get("/view/req-1").text
    for expected in ("HOLD", "SCOPE_CREEP", "UNBOUND", "SUBSTITUTION",
                     "Custodian derived", "reproduces exactly", "chain intact"):
        assert expected in page, expected


def test_the_viewer_shows_the_gap_between_claim_and_derivation(client):
    forged = [dict(CLEAN_CART[0], asserted_unit_price_paise=9_900), CLEAN_CART[1]]
    verify(client, forged)
    page = client.get("/view/req-1").text
    assert "₹443.00" in page and "₹643.00" in page   # asserted vs derived


def test_the_viewer_names_what_needed_a_model(client):
    verify(client, CLEAN_CART)
    assert "decided by arithmetic" in client.get("/view/req-1").text


def test_the_index_lists_decisions(client):
    verify(client, CLEAN_CART, request_id="a", key="ka")
    verify(client, CLEAN_CART + [WOK], request_id="b", key="kb")
    page = client.get("/").text
    assert "/view/a" in page and "/view/b" in page


def test_an_unknown_request_renders_a_404_page(client):
    response = client.get("/view/nope")
    assert response.status_code == 404 and "No such request" in response.text


def test_capture_refuses_an_order_nobody_has_paid(client):
    """No API call makes a payment happen, so capture must not assume one did."""
    verify(client, CLEAN_CART)
    assert client.post("/v1/checkout/settle/req-1").json()["order"]["amount_paise"] == 64_300

    response = client.post("/v1/checkout/capture/req-1")
    assert response.status_code == 409
    assert "nobody has paid" in response.json()["detail"]


def test_capture_without_an_open_order_is_refused(client):
    verify(client, CLEAN_CART)
    response = client.post("/v1/checkout/capture/req-1")
    assert response.status_code == 409
    assert "no order open" in response.json()["detail"]


# --- the payer's page and its signed callback ------------------------------

def test_the_checkout_page_is_only_offered_with_a_live_gateway(client):
    """The in-process gateway has no hosted page, and saying so beats a broken one."""
    verify(client, CLEAN_CART)
    client.post("/v1/checkout/settle/req-1")
    assert client.get("/checkout/req-1").status_code == 409


def test_a_callback_with_no_open_order_is_refused(client):
    verify(client, CLEAN_CART)
    response = client.post("/v1/checkout/callback/req-1", json={
        "razorpay_order_id": "order_x", "razorpay_payment_id": "pay_x",
        "razorpay_signature": "x" * 64})
    assert response.status_code == 409
