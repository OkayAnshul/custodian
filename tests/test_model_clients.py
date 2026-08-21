"""The two live model clients, exercised without a network.

Neither `ClaudeParser` nor `ClaudeScorer` had ever been executed. That is the
shape of BROKE.md 006 — code that only runs against a credential nobody has is
code nobody has run — so the stubs below mirror the SDK's real response objects
closely enough that a mismatch in request shape or response handling fails here
rather than on the day.

What this does not test is the network and the model's judgment. It tests every
line of ours that surrounds them.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from custodian.gate.semantic import ClaudeScorer, ScoringError
from custodian.intent.claude import ClaudeParser
from custodian.intent.parser import ParseError
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem
from custodian.schemas.verdict import VerdictLabel


@dataclass
class _Block:
    type: str
    text: str


@dataclass
class _Response:
    """Mirrors the shape of anthropic.types.Message that our code reads."""

    content: list[_Block]
    stop_reason: str = "end_turn"
    stop_details: Any = None


@dataclass
class _StubMessages:
    payload: dict | None = None
    stop_reason: str = "end_turn"
    raises: Exception | None = None
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        text = json.dumps(self.payload) if self.payload is not None else ""
        blocks = [_Block("thinking", ""), _Block("text", text)] if text else []
        return _Response(content=blocks, stop_reason=self.stop_reason)


@dataclass
class _StubClient:
    messages: _StubMessages


def _requested():
    return RequestedItem(line_id="r1", raw_text="whole turmeric", base="turmeric",
                         form="whole", category="spices")


def _offered():
    return CatalogItem(item_id="SKU032", name="Everest Haldi Powder 100gm", raw_name="x",
                       price_paise=4_200, in_stock=True, base="turmeric", form="powder",
                       category="spices")


# --- the substitution scorer ----------------------------------------------

def test_a_verdict_round_trips_from_a_model_response():
    stub = _StubMessages(payload={"label": "FAITHFUL", "score_bp": 8_800,
                                  "rationale": "ground works in a paste"})
    scorer = ClaudeScorer(client=_StubClient(stub))
    verdict = scorer.score(goal="thai curry", requested=_requested(), offered=_offered(),
                           cart_line_id="l1")

    assert verdict.label is VerdictLabel.FAITHFUL
    assert verdict.score_bp == 8_800
    assert verdict.model == "claude-opus-5"
    assert json.loads(verdict.raw_response)["rationale"]


def test_the_request_constrains_the_output_to_a_schema():
    """Free-form text is not accepted, so 'the model returned junk' is not a runtime case."""
    stub = _StubMessages(payload={"label": "UNSURE", "score_bp": 5_000, "rationale": "depends"})
    ClaudeScorer(client=_StubClient(stub)).score(
        goal="g", requested=_requested(), offered=_offered(), cart_line_id="l1")

    sent = stub.calls[0]
    fmt = sent["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert set(fmt["schema"]["properties"]) == {"label", "score_bp", "rationale"}
    assert sent["thinking"] == {"type": "adaptive"}


def test_the_model_is_never_shown_a_price_a_budget_or_a_mandate():
    """It judges substitution fidelity and cannot see what a purchase decision needs.

    Checks the question, not the whole request: the system prompt legitimately
    names those things in order to tell the model it cannot see them.
    """
    stub = _StubMessages(payload={"label": "FAITHFUL", "score_bp": 9_000, "rationale": "ok"})
    ClaudeScorer(client=_StubClient(stub)).score(
        goal="thai curry", requested=_requested(), offered=_offered(), cart_line_id="l1")

    question = json.dumps(stub.calls[0]["messages"]).lower()
    for forbidden in ("price", "budget", "mandate", "paise", "4200", "₹"):
        assert forbidden not in question, f"{forbidden!r} reached the model"

    # And it does see what it needs to judge the substitution.
    for expected in ("turmeric", "whole", "powder", "thai curry"):
        assert expected in question


def test_a_refusal_is_an_error_not_a_verdict():
    stub = _StubMessages(payload={"label": "FAITHFUL", "score_bp": 9_000, "rationale": "x"},
                         stop_reason="refusal")
    with pytest.raises(ScoringError, match="declined"):
        ClaudeScorer(client=_StubClient(stub)).score(
            goal="g", requested=_requested(), offered=_offered(), cart_line_id="l1")


def test_an_unusable_payload_is_reported_not_repaired():
    stub = _StubMessages(payload={"label": "MAYBE", "score_bp": 5_000, "rationale": "x"})
    with pytest.raises(ScoringError, match="not a usable verdict"):
        ClaudeScorer(client=_StubClient(stub)).score(
            goal="g", requested=_requested(), offered=_offered(), cart_line_id="l1")


def test_an_empty_response_is_an_error():
    stub = _StubMessages(payload=None)
    with pytest.raises(ScoringError, match="no text"):
        ClaudeScorer(client=_StubClient(stub)).score(
            goal="g", requested=_requested(), offered=_offered(), cart_line_id="l1")


def _http_error(cls, message: str):
    """Build a real SDK exception. They require a response object to construct."""
    import httpx2 as httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx.Response(429, request=request), body=None)


def test_a_transport_failure_is_not_read_as_a_decline():
    """A timeout and a refusal are different things and must not collapse."""
    import anthropic
    import httpx2 as httpx

    stub = _StubMessages(raises=anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")))
    with pytest.raises(ScoringError, match="could not reach"):
        ClaudeScorer(client=_StubClient(stub)).score(
            goal="g", requested=_requested(), offered=_offered(), cart_line_id="l1")


# --- the intent parser -----------------------------------------------------

PARSED = {
    "goal": "ingredients for a thai curry, under Rs 2000", "budget_paise": 200_000,
    "merchant_scope": ["kirana-blr-001"], "category_scope": None,
    "substitution_policy": "SAME_BASE",
    "requested_items": [{"raw_text": "coconut milk", "quantity": 2,
                         "max_unit_price_paise": None}],
}


def test_an_intent_round_trips_from_a_model_response():
    stub = _StubMessages(payload=PARSED)
    result = ClaudeParser(client=_StubClient(stub)).parse(PARSED["goal"], intent_id="i1")

    assert result.intent.budget_paise == 200_000
    assert result.model == "claude-opus-5"
    assert result.prompt_digest
    # The model supplied the words; the taxonomy decided what they are.
    assert result.intent.requested_items[0].base == "coconut"


def test_the_parser_constrains_its_output_too():
    stub = _StubMessages(payload=PARSED)
    ClaudeParser(client=_StubClient(stub)).parse(PARSED["goal"], intent_id="i1")
    fmt = stub.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False


def test_an_empty_request_is_refused_before_the_model_is_called():
    stub = _StubMessages(payload=PARSED)
    with pytest.raises(ParseError, match="empty request"):
        ClaudeParser(client=_StubClient(stub)).parse("   ", intent_id="i1")
    assert not stub.calls


def test_a_parser_refusal_surfaces_its_category():
    stub = _StubMessages(payload=PARSED, stop_reason="refusal")
    with pytest.raises(ParseError, match="declined"):
        ClaudeParser(client=_StubClient(stub)).parse(PARSED["goal"], intent_id="i1")


def test_rate_limiting_is_distinguished_from_a_bad_request():
    import anthropic

    stub = _StubMessages(raises=_http_error(anthropic.RateLimitError, "slow down"))
    with pytest.raises(ParseError, match="rate limited"):
        ClaudeParser(client=_StubClient(stub)).parse(PARSED["goal"], intent_id="i1")
