"""The contract every IntentParser must satisfy, whichever provider is behind it.

Model position #1, graded the way position #2 already is. `ClaudeParser` and
`GroqParser` are held to identical assertions against stubs shaped like each
provider's real response objects, so the gate's first model dependency is as
swappable as its second — and with both Groq implementations present, the whole
system runs end to end on a free tier.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from custodian.intent import prompt as prompt_module
from custodian.intent.claude import ClaudeParser
from custodian.intent.groq_parser import GroqParser
from custodian.intent.parser import IntentParser, ParseError
from custodian.schemas.intent import SubstitutionPolicy

pytestmark = pytest.mark.contract

GOAL = "ingredients for a thai curry, under Rs 2000"
PAYLOAD = {
    "goal": GOAL, "budget_paise": 200_000, "merchant_scope": ["kirana-blr-001"],
    "category_scope": None, "substitution_policy": "SAME_BASE",
    "requested_items": [
        {"raw_text": "coconut milk", "quantity": 2, "max_unit_price_paise": None},
        {"raw_text": "thai red curry paste", "quantity": 1, "max_unit_price_paise": None},
    ],
}


@dataclass
class _Block:
    type: str
    text: str


@dataclass
class _AnthropicResponse:
    content: list
    stop_reason: str = "end_turn"
    stop_details: Any = None


@dataclass
class _AnthropicStub:
    payload: dict | None = None
    calls: list = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(self.payload) if self.payload is not None else ""
        return _AnthropicResponse(content=[_Block("text", text)] if text else [])


@dataclass
class _GroqMessage:
    content: str


@dataclass
class _GroqChoice:
    message: _GroqMessage
    finish_reason: str = "stop"


@dataclass
class _GroqResponse:
    choices: list


@dataclass
class _GroqStub:
    payload: dict | None = None
    calls: list = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(self.payload) if self.payload is not None else ""
        return _GroqResponse(choices=[_GroqChoice(_GroqMessage(text))] if text else [])


def _build(provider: str, *, payload=None):
    if provider == "claude":
        stub = _AnthropicStub(payload=payload)
        return ClaudeParser(client=type("C", (), {"messages": stub})()), stub
    stub = _GroqStub(payload=payload)
    completions = type("Completions", (), {"create": stub.create})()
    chat = type("Chat", (), {"completions": completions})()
    return GroqParser(client=type("G", (), {"chat": chat})()), stub


@pytest.fixture(params=["claude", "groq"])
def provider(request) -> str:
    return request.param


# --- the contract ----------------------------------------------------------

def test_satisfies_the_protocol(provider):
    parser, _ = _build(provider, payload=PAYLOAD)
    assert isinstance(parser, IntentParser)
    assert parser.model


def test_an_intent_round_trips(provider):
    parser, _ = _build(provider, payload=PAYLOAD)
    result = parser.parse(GOAL, intent_id="i1")
    assert result.intent.budget_paise == 200_000
    assert len(result.intent.requested_items) == 2
    assert result.intent.substitution_policy is SubstitutionPolicy.SAME_BASE


def test_the_model_supplies_words_and_the_taxonomy_decides_what_they_are(provider):
    """One vocabulary on both sides, whoever did the parsing."""
    parser, _ = _build(provider, payload=PAYLOAD)
    placed = {i.raw_text: (i.base, i.form)
              for i in parser.parse(GOAL, intent_id="i1").intent.requested_items}
    assert placed["coconut milk"] == ("coconut", "milk")
    assert placed["thai red curry paste"] == ("thai-curry", "paste")


def test_the_humans_own_words_are_preserved(provider):
    parser, _ = _build(provider, payload=PAYLOAD)
    assert parser.parse(GOAL, intent_id="i1").intent.requested_items[0].raw_text == "coconut milk"


def test_the_prompt_digest_is_the_same_question_whoever_is_asked(provider):
    parser, _ = _build(provider, payload=PAYLOAD)
    assert parser.parse(GOAL, intent_id="i1").prompt_digest == prompt_module.prompt_digest(GOAL)


def test_the_raw_response_is_kept(provider):
    parser, _ = _build(provider, payload=PAYLOAD)
    result = parser.parse(GOAL, intent_id="i1")
    assert json.loads(result.raw_response)["goal"] == GOAL
    assert result.as_observed()["model"] == parser.model


def test_the_output_is_constrained_to_the_schema(provider):
    parser, stub = _build(provider, payload=PAYLOAD)
    parser.parse(GOAL, intent_id="i1")
    sent = json.dumps(stub.calls[0])
    assert "json_schema" in sent
    assert "requested_items" in sent
    assert '"additionalProperties": false' in sent or '"additionalProperties":false' in sent


def test_the_model_is_never_asked_to_categorise(provider):
    """Category comes from the lexicon, not a second opinion about words."""
    parser, stub = _build(provider, payload=PAYLOAD)
    parser.parse(GOAL, intent_id="i1")
    schema = json.dumps(stub.calls[0])
    assert '"base"' not in schema and '"category"' not in schema.replace('"category_scope"', "")


def test_an_empty_request_is_refused_before_the_model_is_called(provider):
    parser, stub = _build(provider, payload=PAYLOAD)
    with pytest.raises(ParseError, match="empty request"):
        parser.parse("   ", intent_id="i1")
    assert not stub.calls


def test_an_empty_response_is_an_error(provider):
    parser, _ = _build(provider, payload=None)
    with pytest.raises(ParseError):
        parser.parse(GOAL, intent_id="i1")


def test_a_payload_that_violates_the_contract_is_refused(provider):
    parser, _ = _build(provider, payload=dict(PAYLOAD, budget_paise=-1))
    with pytest.raises(ParseError, match="does not satisfy"):
        parser.parse(GOAL, intent_id="i1")


def test_a_payload_with_no_items_is_refused(provider):
    parser, _ = _build(provider, payload=dict(PAYLOAD, requested_items=[]))
    with pytest.raises(ParseError, match="no requested items"):
        parser.parse(GOAL, intent_id="i1")


# --- swappability ----------------------------------------------------------

def test_both_providers_produce_the_same_intent():
    """The gate consumes this. If the shapes differ, the swap is a lie."""
    claude, _ = _build("claude", payload=PAYLOAD)
    groq, _ = _build("groq", payload=PAYLOAD)
    a = claude.parse(GOAL, intent_id="i1").intent
    b = groq.parse(GOAL, intent_id="i1").intent

    assert a.canonical() == b.canonical()


def test_the_whole_system_has_a_free_tier_path():
    """Both model positions have a Groq implementation, so no paid key is required."""
    from custodian.gate.groq_scorer import GroqScorer
    from custodian.gate.semantic import SemanticScorer

    assert isinstance(GroqParser(client=object()), IntentParser)
    assert isinstance(GroqScorer(client=object()), SemanticScorer)
