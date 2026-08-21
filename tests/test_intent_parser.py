"""The contract every IntentParser must satisfy, plus the resolve step."""

import json

import pytest

from custodian.intent import prompt as prompt_module
from custodian.intent.parser import IntentParser, ParseError, decode, resolve
from custodian.intent.recorded import RecordedParser
from custodian.schemas.catalog import UNKNOWN
from custodian.schemas.intent import SubstitutionPolicy

GOAL = "ingredients for a thai curry, under ₹2,000"

PAYLOAD = {
    "goal": GOAL,
    "budget_paise": 200_000,
    "merchant_scope": ["kirana-blr-001"],
    "category_scope": None,
    "substitution_policy": "SAME_BASE",
    "requested_items": [
        {"raw_text": "coconut milk", "quantity": 2, "max_unit_price_paise": None},
        {"raw_text": "thai red curry paste", "quantity": 1, "max_unit_price_paise": None},
        {"raw_text": "lemongrass", "quantity": 1, "max_unit_price_paise": None},
    ],
}


@pytest.fixture
def parser() -> RecordedParser:
    p = RecordedParser()
    p.record(GOAL, PAYLOAD)
    return p


def test_satisfies_the_protocol(parser):
    assert isinstance(parser, IntentParser)
    assert parser.model


def test_parses_a_recorded_request(parser):
    result = parser.parse(GOAL, intent_id="int-1")
    assert result.intent.budget_paise == 200_000
    assert len(result.intent.requested_items) == 3
    assert result.intent.substitution_policy is SubstitutionPolicy.SAME_BASE


# --- the division of labour ------------------------------------------------

def test_the_model_supplies_words_and_the_taxonomy_decides_what_they_are(parser):
    """One vocabulary on both sides, or the comparison is meaningless."""
    items = parser.parse(GOAL, intent_id="int-1").intent.requested_items
    placed = {item.raw_text: (item.base, item.form) for item in items}
    assert placed["coconut milk"] == ("coconut", "milk")
    assert placed["thai red curry paste"] == ("thai-curry", "paste")


def test_the_humans_own_words_are_preserved(parser):
    """Normalising the request text would lose what was actually asked for."""
    items = parser.parse(GOAL, intent_id="int-1").intent.requested_items
    assert items[0].raw_text == "coconut milk"


def test_an_unplaceable_request_item_is_unknown_not_guessed():
    payload = dict(PAYLOAD, requested_items=[{"raw_text": "novelty glitter pens", "quantity": 1}])
    intent = resolve(payload, intent_id="int-1")
    assert intent.requested_items[0].base == UNKNOWN


# --- provenance ------------------------------------------------------------

def test_the_prompt_digest_identifies_the_exact_prompt(parser):
    result = parser.parse(GOAL, intent_id="int-1")
    assert result.prompt_digest == prompt_module.prompt_digest(GOAL)


def test_changing_the_prompt_version_invalidates_recorded_fixtures(parser, monkeypatch):
    """A fixture recorded under another prompt must not silently satisfy this one."""
    monkeypatch.setattr(prompt_module, "VERSION", "intent-prompt-v99")
    with pytest.raises(ParseError, match="prompt version changed"):
        parser.parse(GOAL, intent_id="int-1")


def test_the_raw_response_is_kept_because_a_parsed_object_is_not_evidence(parser):
    result = parser.parse(GOAL, intent_id="int-1")
    assert json.loads(result.raw_response)["goal"] == GOAL
    assert result.as_observed()["prompt_version"] == prompt_module.VERSION
    assert result.as_observed()["model"] == "recorded"


def test_an_unrecorded_goal_is_an_error_not_an_invention(parser):
    with pytest.raises(ParseError, match="no recorded response"):
        parser.parse("something never recorded", intent_id="int-1")


# --- malformed model output ------------------------------------------------

def test_invalid_json_is_reported_not_repaired():
    with pytest.raises(ParseError, match="not valid JSON"):
        decode("{not json")


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"goal": "x", "requested_items": []}, "no requested items"),
        ({"goal": "x", "requested_items": [{"quantity": 1}]}, "no raw_text"),
        ({"goal": "x"}, "no requested items"),
    ],
)
def test_malformed_payloads_raise_rather_than_being_patched_up(payload, message):
    """A parser that quietly fixes model output is deciding what the human meant."""
    with pytest.raises(ParseError, match=message):
        resolve(payload, intent_id="int-1")


def test_a_payload_that_violates_the_intent_contract_is_refused():
    payload = dict(PAYLOAD, budget_paise=-1)
    with pytest.raises(ParseError, match="does not satisfy the intent contract"):
        resolve(payload, intent_id="int-1")


def test_missing_substitution_policy_defaults_to_the_conservative_one():
    payload = {k: v for k, v in PAYLOAD.items() if k != "substitution_policy"}
    assert resolve(payload, intent_id="i").substitution_policy is SubstitutionPolicy.SAME_BASE


# --- the prompt itself -----------------------------------------------------

def test_the_prompt_does_not_ask_the_model_to_categorise():
    """Category comes from the lexicon, not from a second opinion about words."""
    assert "category_scope" in prompt_module.OUTPUT_SCHEMA["properties"]
    item_schema = prompt_module.OUTPUT_SCHEMA["properties"]["requested_items"]["items"]
    assert set(item_schema["properties"]) == {"raw_text", "quantity", "max_unit_price_paise"}


def test_the_output_schema_forbids_extra_properties():
    assert prompt_module.OUTPUT_SCHEMA["additionalProperties"] is False


def test_the_prompt_digest_covers_everything_that_determined_the_input(monkeypatch):
    before = prompt_module.prompt_digest(GOAL)
    monkeypatch.setattr(prompt_module, "SYSTEM", prompt_module.SYSTEM + " extra rule")
    assert prompt_module.prompt_digest(GOAL) != before
