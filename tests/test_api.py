"""The merchant endpoint, end to end."""

import os

import pytest
from fastapi.testclient import TestClient

from custodian.api.app import create_app

HAS_LIVE_KEYS = bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))

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


def test_a_link_the_provider_will_not_mint_does_not_fail_the_settlement():
    """The payable URL is a convenience; the order is the settlement.

    Link creation is rate limited far more tightly than order creation, so a
    provider that refuses one must not take the settle call down with it. The
    order is open and the amount is fixed — what is missing is a URL.
    """
    from custodian.payments.fake import FakeGateway
    from custodian.payments.gateway import PaymentError

    class _NoLinks(FakeGateway):
        def payment_link_for(self, order):
            raise PaymentError("razorpay: could not create payment link: too many requests")

    client = TestClient(create_app(gateway=_NoLinks()))
    verify(client, CLEAN_CART)
    settled = client.post("/v1/checkout/settle/req-1")
    assert settled.status_code == 200
    assert settled.json()["payment_url"] is None
    assert settled.json()["order"]["amount_paise"] == 64_300


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


def test_the_served_app_uses_the_fake_without_credentials(monkeypatch):
    """`create_app` defaults to the fake; the served process reads the env.

    Both halves matter. A test suite that picked up a stray credential would
    start calling a payment provider — and `make test` sources `.env`, so that
    is not hypothetical. A served process that ignored the credential could not
    host the checkout page at all, because the page embeds a live key.
    """
    from custodian.api.app import _gateway_from_env

    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    assert _gateway_from_env().name == "fake"

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_notatestkey")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "whatever")
    assert _gateway_from_env().name == "fake", "a live key must not be served"


@pytest.mark.live
@pytest.mark.skipif(not HAS_LIVE_KEYS, reason="no Razorpay test credentials")
def test_the_served_app_uses_the_live_gateway_when_credentials_are_present():
    """The condition that makes the documented `make serve` walkthrough possible."""
    from custodian.api.app import _gateway_from_env

    assert _gateway_from_env().name == "razorpay-test"


@pytest.mark.live
@pytest.mark.skipif(not HAS_LIVE_KEYS, reason="no Razorpay test credentials")
def test_the_checkout_page_carries_the_order_a_payer_would_actually_pay():
    """The page, rendered against a real order, with the live gateway attached.

    What a browser adds beyond this is Razorpay's own script and a person with
    a card, and neither is testable here. What is testable is everything the
    page depends on being right before the browser gets it: the order id is the
    one the provider issued, the amount is the one Custodian derived rather than
    the one the agent asserted, and the callback posts back to this request.

    `LIMITATIONS.md` still says the browser leg is unrun, because it is.
    """
    from custodian.payments.razorpay_client import RazorpayGateway

    client = TestClient(create_app(gateway=RazorpayGateway()))
    verify(client, CLEAN_CART)
    settled = client.post("/v1/checkout/settle/req-1").json()
    assert settled["order"]["order_id"].startswith("order_")
    assert settled["order"]["amount_paise"] == 64_300

    page = client.get("/checkout/req-1")
    assert page.status_code == 200
    assert settled["order"]["order_id"] in page.text
    assert os.environ["RAZORPAY_KEY_ID"] in page.text
    assert "checkout.razorpay.com/v1/checkout.js" in page.text
    assert "/v1/checkout/callback/req-1" in page.text


def test_a_callback_with_no_open_order_is_refused(client):
    verify(client, CLEAN_CART)
    response = client.post("/v1/checkout/callback/req-1", json={
        "razorpay_order_id": "order_x", "razorpay_payment_id": "pay_x",
        "razorpay_signature": "x" * 64})
    assert response.status_code == 409
