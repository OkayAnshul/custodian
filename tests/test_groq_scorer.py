"""Groq-specific behaviour. The shared contract lives in tests/contract/."""

import json
from dataclasses import dataclass, field

import groq
import httpx2 as httpx
import pytest

from custodian.gate.groq_scorer import DEFAULT_MODEL, STRICT_MODELS, GroqScorer
from custodian.gate.semantic import ScoringError
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"


@dataclass
class _Response:
    choices: list


@dataclass
class _Stub:
    payload: dict | None = None
    raises: Exception | None = None
    finish_reason: str = "stop"
    #: Bypasses `payload`, for responses that are not valid JSON at all.
    raw_text: str | None = None
    calls: list = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        if self.raw_text is not None:
            return _Response(choices=[_Choice(_Message(self.raw_text), self.finish_reason)])
        text = json.dumps(self.payload) if self.payload is not None else ""
        return _Response(choices=[_Choice(_Message(text), self.finish_reason)])


def build(**kwargs):
    stub = _Stub(**kwargs)
    completions = type("Completions", (), {"create": stub.create})()
    chat = type("Chat", (), {"completions": completions})()
    return GroqScorer(client=type("G", (), {"chat": chat})()), stub


def _score(scorer):
    return scorer.score(
        goal="thai curry",
        requested=RequestedItem(line_id="r1", raw_text="whole turmeric", base="turmeric",
                                form="whole", category="spices"),
        offered=CatalogItem(item_id="SKU032", name="Haldi Powder 100gm", raw_name="x",
                            price_paise=4_200, in_stock=True, base="turmeric",
                            form="powder", category="spices"),
        cart_line_id="l1")


VERDICT = {"label": "FAITHFUL", "score_bp": 8_800, "rationale": "fine in a paste"}


def _http(cls, message: str, status: int = 429):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls(message, response=httpx.Response(status, request=request), body=None)


# --- the strict-model guard ------------------------------------------------

def test_the_default_model_enforces_the_schema():
    assert DEFAULT_MODEL in STRICT_MODELS


def test_a_model_that_cannot_enforce_the_schema_is_refused():
    """Without strict decoding, 'the output is constrained' is a hope."""
    with pytest.raises(ScoringError, match="strict schema enforcement"):
        GroqScorer(model_id="llama-3.3-70b-versatile", client=object())


def test_the_refusal_names_the_models_that_would_work():
    with pytest.raises(ScoringError, match="gpt-oss-120b"):
        GroqScorer(model_id="mixtral-8x7b-32768", client=object())


# --- the request -----------------------------------------------------------

def test_the_system_prompt_travels_as_a_message_not_a_parameter():
    """Groq's wire format differs from Anthropic's; this is where it differs."""
    scorer, stub = build(payload=VERDICT)
    _score(scorer)
    roles = [m["role"] for m in stub.calls[0]["messages"]]
    assert roles == ["system", "user"]
    assert "system" not in stub.calls[0]


def test_strict_is_actually_requested():
    scorer, stub = build(payload=VERDICT)
    _score(scorer)
    schema = stub.calls[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["name"] == "substitution_verdict"


def test_the_temperature_is_zero_so_a_verdict_does_not_move():
    """A verdict that changes on re-ask is one the ledger cannot stand behind."""
    scorer, stub = build(payload=VERDICT)
    _score(scorer)
    assert stub.calls[0]["temperature"] == 0.0


# --- failure modes ---------------------------------------------------------

def test_a_rate_limit_says_so():
    """Free tiers rate-limit. A rate limit means wait; a refusal means hold."""
    scorer, _ = build(raises=_http(groq.RateLimitError, "slow down"))
    with pytest.raises(ScoringError, match="rate limited"):
        _score(scorer)


def test_a_transport_failure_is_not_read_as_a_decline():
    scorer, _ = build(raises=groq.APIConnectionError(
        request=httpx.Request("POST", "https://api.groq.com/")))
    with pytest.raises(ScoringError, match="could not reach"):
        _score(scorer)


def test_a_server_error_reports_its_status():
    scorer, _ = build(raises=_http(groq.InternalServerError, "boom", status=500))
    with pytest.raises(ScoringError, match="500"):
        _score(scorer)


def test_a_truncated_response_says_it_was_cut_off():
    """Truncated JSON parses as malformed; naming the real cause beats that."""
    scorer, _ = build(payload=VERDICT, finish_reason="length")
    with pytest.raises(ScoringError, match="cut off"):
        _score(scorer)


def test_malformed_json_is_reported_as_such():
    """Strict decoding should prevent this; the handler exists for when it does not."""
    scorer, _ = build(raw_text='{"label": "FAITH')
    with pytest.raises(ScoringError, match="not valid JSON"):
        _score(scorer)
