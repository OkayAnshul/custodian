"""The contract every SemanticScorer must satisfy, whichever provider is behind it.

This is the file that turns "the model is a component, not the system" from a
sentence in the README into something checkable. `ClaudeScorer` and `GroqScorer`
are graded here by identical assertions, against stubs shaped like each
provider's real response objects. The gate does not know which one ran, and
neither does this suite past the fixture.

The provider-specific quirks — Anthropic's refusal stop_reason, Groq's strict-
model list — live in their own tests. What lives here is everything the gate
depends on, which is exactly what must not vary.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from custodian.gate.groq_scorer import GroqScorer
from custodian.gate.semantic import ScoringError, SemanticScorer, prompt_digest
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem
from custodian.schemas.verdict import VerdictLabel

pytestmark = pytest.mark.contract

VERDICT = {"label": "FAITHFUL", "score_bp": 8_800, "rationale": "ground works in a paste"}


# --- provider-shaped stubs -------------------------------------------------

@dataclass
class _AnthropicBlock:
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
    raises: Exception | None = None
    calls: list = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        text = json.dumps(self.payload) if self.payload is not None else ""
        return _AnthropicResponse(
            content=[_AnthropicBlock("text", text)] if text else []
        )


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
    raises: Exception | None = None
    calls: list = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        text = json.dumps(self.payload) if self.payload is not None else ""
        return _GroqResponse(choices=[_GroqChoice(_GroqMessage(text))] if text else [])


def _build(provider: str, *, payload=None, raises=None):
    """Return (scorer, stub) for one provider."""
    if provider == "claude":
        from custodian.intent.claude import ClaudeParser  # noqa: F401 — same SDK surface
        from custodian.gate.semantic import ClaudeScorer

        stub = _AnthropicStub(payload=payload, raises=raises)
        return ClaudeScorer(client=type("C", (), {"messages": stub})()), stub

    stub = _GroqStub(payload=payload, raises=raises)
    completions = type("Completions", (), {"create": stub.create})()
    chat = type("Chat", (), {"completions": completions})()
    return GroqScorer(client=type("G", (), {"chat": chat})()), stub


@pytest.fixture(params=["claude", "groq"])
def provider(request) -> str:
    return request.param


def requested():
    return RequestedItem(line_id="r1", raw_text="whole turmeric", base="turmeric",
                         form="whole", category="spices")


def offered():
    return CatalogItem(item_id="SKU032", name="Everest Haldi Powder 100gm", raw_name="x",
                       price_paise=4_200, in_stock=True, base="turmeric", form="powder",
                       category="spices")


def score(scorer):
    return scorer.score(goal="thai curry", requested=requested(), offered=offered(),
                        cart_line_id="l1")


# --- the contract ----------------------------------------------------------

def test_satisfies_the_protocol(provider):
    scorer, _ = _build(provider, payload=VERDICT)
    assert isinstance(scorer, SemanticScorer)
    assert scorer.model


def test_a_verdict_round_trips(provider):
    scorer, _ = _build(provider, payload=VERDICT)
    verdict = score(scorer)
    assert verdict.label is VerdictLabel.FAITHFUL
    assert verdict.score_bp == 8_800
    assert verdict.cart_line_id == "l1" and verdict.requested_line_id == "r1"


def test_the_verdict_names_the_model_that_produced_it(provider):
    scorer, _ = _build(provider, payload=VERDICT)
    assert score(scorer).model == scorer.model


def test_the_raw_response_is_kept(provider):
    """A parsed object is our reading of the answer, not the answer."""
    scorer, _ = _build(provider, payload=VERDICT)
    assert json.loads(score(scorer).raw_response)["rationale"] == VERDICT["rationale"]


def test_the_prompt_digest_is_the_same_question_whoever_is_asked(provider):
    """One question, two providers, one digest — which is what lets a ledger
    show the same substitution answered two ways."""
    scorer, _ = _build(provider, payload=VERDICT)
    assert score(scorer).prompt_digest == prompt_digest("thai curry", requested(), offered())


def test_unsure_is_available_and_is_not_usable(provider):
    scorer, _ = _build(provider, payload={"label": "UNSURE", "score_bp": 5_000,
                                          "rationale": "depends on the dish"})
    verdict = score(scorer)
    assert verdict.label is VerdictLabel.UNSURE and not verdict.usable


def test_the_output_is_constrained_to_the_schema(provider):
    """Free-form text is not accepted, whichever provider is behind it."""
    scorer, stub = _build(provider, payload=VERDICT)
    score(scorer)
    sent = json.dumps(stub.calls[0])
    assert "json_schema" in sent
    assert '"additionalProperties": false' in sent or '"additionalProperties":false' in sent
    for field_name in ("label", "score_bp", "rationale"):
        assert field_name in sent


def test_the_model_never_sees_a_price_a_budget_or_a_mandate(provider):
    """It judges substitution fidelity and cannot see what a purchase needs.

    Checked against the question only: the system prompt names those things in
    order to tell the model it cannot see them.
    """
    scorer, stub = _build(provider, payload=VERDICT)
    score(scorer)
    call = stub.calls[0]
    question = json.dumps([m for m in call["messages"] if m["role"] == "user"]).lower()
    for forbidden in ("price", "budget", "mandate", "paise", "4200", "₹"):
        assert forbidden not in question, f"{forbidden!r} reached the model"
    for expected in ("turmeric", "whole", "powder", "thai curry"):
        assert expected in question


def test_an_unusable_payload_is_reported_not_repaired(provider):
    scorer, _ = _build(provider, payload={"label": "MAYBE", "score_bp": 5_000,
                                          "rationale": "x"})
    with pytest.raises(ScoringError):
        score(scorer)


def test_an_empty_response_is_an_error(provider):
    scorer, _ = _build(provider, payload=None)
    with pytest.raises(ScoringError):
        score(scorer)


def test_a_score_outside_the_scale_is_refused(provider):
    scorer, _ = _build(provider, payload={"label": "FAITHFUL", "score_bp": 99_999,
                                          "rationale": "x"})
    with pytest.raises(ScoringError):
        score(scorer)


# --- swappability, which is the point --------------------------------------

def test_both_providers_produce_the_same_verdict_shape():
    """The gate consumes this. If the shapes differ, the swap is a lie."""
    claude, _ = _build("claude", payload=VERDICT)
    groq, _ = _build("groq", payload=VERDICT)
    a, b = score(claude), score(groq)

    assert a.label is b.label
    assert a.score_bp == b.score_bp
    assert a.prompt_digest == b.prompt_digest      # same question
    assert a.model != b.model                      # different answerer
    assert set(a.canonical()) == set(b.canonical())


def test_the_gate_reaches_the_same_decision_whichever_scored_it():
    """decide() does not know which provider ran, and its output proves it."""
    from custodian.canonical import canonical_hash
    from custodian.gate.decide import decide
    from custodian.gate.substitution import SubstitutionTables
    from custodian.gate.thresholds import DEFAULT
    from custodian.ingest.snapshot import ingest_csv
    from custodian.ingest.taxonomy import default_taxonomy
    from custodian.intent.parser import resolve
    from custodian.schemas.cart import Cart, CartLine
    from custodian.schemas.decision_input import DecisionInput
    from custodian.schemas.mandate import Mandate

    now = "2026-08-30T09:00:00+00:00"
    snapshot, _ = ingest_csv("data/catalog/kirana_export.csv",
                             merchant_id="kirana-blr-001", taken_at=now)
    tables = SubstitutionTables.from_taxonomy(default_taxonomy())
    mandate = Mandate(mandate_id="m", max_amount_paise=10**6,
                      per_transaction_cap_paise=4 * 10**5,
                      valid_from="2026-08-01T00:00:00+00:00",
                      valid_until="2026-09-30T00:00:00+00:00",
                      merchant_allowlist=("kirana-blr-001",))
    intent = resolve({"goal": "thai curry", "budget_paise": 200_000,
                      "merchant_scope": ["kirana-blr-001"],
                      "substitution_policy": "SAME_BASE",
                      "requested_items": [{"raw_text": "whole turmeric", "quantity": 1}]},
                     intent_id="i")
    item = snapshot.find("SKU032")
    cart = Cart(cart_id="c", merchant_id="kirana-blr-001", lines=(
        CartLine(line_id="l1", item_id="SKU032", name_asserted=item.name, quantity=1,
                 asserted_unit_price_paise=item.price_paise, satisfies_line_id="i-r1"),))

    outcomes = []
    for name in ("claude", "groq"):
        scorer, _ = _build(name, payload=VERDICT)
        verdict = scorer.score(goal=intent.goal, requested=intent.requested_items[0],
                               offered=item, cart_line_id="l1")
        inp = DecisionInput(request_id="req", evaluated_at=now, intent=intent, cart=cart,
                            snapshot=snapshot, mandate=mandate,
                            semantic_verdicts=(verdict,), thresholds=DEFAULT)
        decision = decide(inp, tables=tables)
        # The model id is recorded on the verdict, not on the decision, so the
        # decision itself must be byte-identical across providers.
        outcomes.append(canonical_hash(decision.canonical()))

    assert outcomes[0] == outcomes[1]
