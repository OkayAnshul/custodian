"""Real recordings versus authored fixtures, and telling them apart.

Every replay fixture in this project was written by hand until now.
`RecordedScorer` and `RecordedParser` replayed answers nobody received, which
made their names an overstatement — the same shape as BROKE.md 010, where a
label recorded *that* a judgment was made but not *whose*.

These tests cover the distinction: a real recording names the model that
produced it, an authored one cannot, and nothing silently presents the second
as the first.
"""

import json

import pytest

from custodian.gate.semantic import RecordedScorer, load_recordings
from custodian.intent.recorded import RecordedParser
from custodian.intent import prompt as intent_prompt
from custodian.gate.semantic import prompt_digest
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem
from custodian.schemas.verdict import VerdictLabel

GOAL = "buy whole turmeric for a pickle"


def requested():
    return RequestedItem(line_id="r1", raw_text="whole turmeric", base="turmeric",
                         form="whole", category="spices")


def offered():
    return CatalogItem(item_id="SKU032", name="Everest Haldi Powder 100gm", raw_name="x",
                       price_paise=4_200, in_stock=True, base="turmeric", form="powder",
                       category="spices")


@pytest.fixture
def fixture_file(tmp_path):
    verdict_digest = prompt_digest(GOAL, requested(), offered())
    intent_digest = intent_prompt.prompt_digest(GOAL)
    path = tmp_path / "model_responses.json"
    path.write_text(json.dumps({
        "version": "fixtures-v1",
        "entries": [
            {"kind": "verdict", "prompt_digest": verdict_digest, "provider": "groq",
             "model": "openai/gpt-oss-120b", "obtained_at": "2026-08-30T09:00:00+00:00",
             "question": "…", "source": "benign-006",
             "raw_response": json.dumps({"label": "UNSURE", "score_bp": 5_100,
                                         "rationale": "depends on the dish"})},
            {"kind": "intent", "prompt_digest": intent_digest, "provider": "groq",
             "model": "openai/gpt-oss-120b", "obtained_at": "2026-08-30T09:00:00+00:00",
             "question": GOAL, "source": "demo-spice",
             "raw_response": json.dumps({
                 "goal": GOAL, "budget_paise": None, "merchant_scope": [],
                 "category_scope": None, "substitution_policy": "SAME_BASE",
                 "requested_items": [{"raw_text": "whole turmeric", "quantity": 1,
                                      "max_unit_price_paise": None}]})},
        ],
    }))
    return path


# --- the distinction -------------------------------------------------------

def test_an_authored_fixture_names_no_model():
    """It cannot: nobody answered."""
    scorer = RecordedScorer()
    scorer.record(GOAL, requested(), offered(),
                  {"label": "UNSURE", "score_bp": 5_000, "rationale": "x"})
    assert not scorer.has_real_recordings
    verdict = scorer.score(goal=GOAL, requested=requested(), offered=offered(),
                           cart_line_id="l1")
    assert verdict.model == "recorded"


def test_a_real_recording_names_the_model_that_produced_it(fixture_file):
    scorer = RecordedScorer.from_recordings(fixture_file)
    assert scorer.has_real_recordings
    verdict = scorer.score(goal=GOAL, requested=requested(), offered=offered(),
                           cart_line_id="l1")
    assert verdict.model == "openai/gpt-oss-120b"
    assert verdict.label is VerdictLabel.UNSURE
    assert verdict.score_bp == 5_100


def test_a_recorded_parse_names_its_model_too(fixture_file):
    parser = RecordedParser.from_recordings(fixture_file)
    assert parser.has_real_recordings
    result = parser.parse(GOAL, intent_id="i1")
    assert result.model == "openai/gpt-oss-120b"
    assert result.intent.requested_items[0].base == "turmeric"


def test_a_missing_fixture_file_degrades_rather_than_failing(tmp_path):
    """A clean clone has no recordings and must still run."""
    scorer = RecordedScorer.from_recordings(tmp_path / "absent.json")
    assert not scorer.has_real_recordings and not scorer.responses


def test_recordings_are_keyed_by_prompt_digest_not_by_goal(fixture_file):
    """A response recorded under a different prompt cannot satisfy this one."""
    scorer = RecordedScorer.from_recordings(fixture_file)
    with pytest.raises(Exception):
        scorer.score(goal="something else entirely", requested=requested(),
                     offered=offered(), cart_line_id="l1")


def test_only_the_requested_kind_is_loaded(fixture_file):
    assert len(load_recordings("verdict", fixture_file)) == 1
    assert len(load_recordings("intent", fixture_file)) == 1
    assert load_recordings("nonsense", fixture_file) == {}


def test_the_shipped_repository_has_no_recordings_yet():
    """Stated as a test so it stops being true the moment it stops being true."""
    from custodian.gate.semantic import FIXTURES_PATH

    if FIXTURES_PATH.exists():
        pytest.skip("recordings exist — someone has run scripts/record_fixtures.py")
    assert not RecordedScorer.from_recordings().has_real_recordings
