"""The flow around the gate, and the replay claim made checkable."""

import pytest

from custodian.gate.decide import decide
from custodian.gate.semantic import RecordedScorer, ScoringError, SemanticScorer
from custodian.gate.service import Custodian
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT, Thresholds
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent.parser import resolve
from custodian.ledger.chain import EventType, Ledger
from custodian.ledger.replay import replay, replay_all
from custodian.ledger.store import ArtifactStore
from custodian.ledger.verify import verify_chain
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.decision import Outcome
from custodian.schemas.intent import RequestedItem
from custodian.schemas.mandate import Mandate
from custodian.schemas.verdict import VerdictLabel

NOW = "2026-08-27T09:00:00+00:00"
COCONUT_MILK, CURRY_PASTE, TURMERIC, WOK = "SKU001", "SKU055", "SKU032", "SKU068"


@pytest.fixture(scope="module")
def snapshot():
    snap, _ = ingest_csv("data/catalog/kirana_export.csv", merchant_id="m1", taken_at=NOW)
    return snap


@pytest.fixture(scope="module")
def tables():
    return SubstitutionTables.from_taxonomy(default_taxonomy())


@pytest.fixture
def mandate():
    return Mandate(mandate_id="mnd", max_amount_paise=1_000_000,
                   per_transaction_cap_paise=300_000,
                   valid_from="2026-08-01T00:00:00+00:00",
                   valid_until="2026-09-30T00:00:00+00:00", merchant_allowlist=("m1",))


@pytest.fixture
def custodian(tables):
    return Custodian(ledger=Ledger.in_memory(), store=ArtifactStore.in_memory(), tables=tables)


def an_intent(items=None, budget=300_000):
    return resolve({"goal": "ingredients for a thai curry, under Rs 2000",
                    "budget_paise": budget, "merchant_scope": ["m1"],
                    "substitution_policy": "SAME_BASE",
                    "requested_items": items or [
                        {"raw_text": "coconut milk", "quantity": 2},
                        {"raw_text": "thai red curry paste", "quantity": 1}]},
                   intent_id="i1")


def a_line(snapshot, line_id, item_id, quantity=1, price=None, satisfies=None):
    item = snapshot.find(item_id)
    return CartLine(line_id=line_id, item_id=item_id, name_asserted=item.name, quantity=quantity,
                    asserted_unit_price_paise=item.price_paise if price is None else price,
                    satisfies_line_id=satisfies)


def run(custodian, snapshot, mandate, lines, *, request_id="req-1", intent=None,
        thresholds=DEFAULT):
    return custodian.evaluate(
        request_id=request_id, intent=intent or an_intent(),
        cart=Cart(cart_id="c1", merchant_id="m1", lines=lines), snapshot=snapshot,
        mandate=mandate, thresholds=thresholds, evaluated_at=NOW,
    )


@pytest.fixture
def clean(snapshot):
    return (a_line(snapshot, "l1", COCONUT_MILK, 2, satisfies="i1-r1"),
            a_line(snapshot, "l2", CURRY_PASTE, 1, satisfies="i1-r2"))


# --- what gets recorded ----------------------------------------------------

def test_a_decision_leaves_a_complete_trail(custodian, snapshot, mandate, clean):
    run(custodian, snapshot, mandate, clean)
    kinds = [e.event_type for e in custodian.ledger.read("req-1")]
    assert kinds == [EventType.INTENT_RECEIVED, EventType.SNAPSHOT_TAKEN, EventType.DECISION_MADE]


def test_what_was_asked_for_is_recorded_before_what_was_concluded(custodian, snapshot, mandate, clean):
    """A dispute starts from the request, so the request has to be in the record."""
    run(custodian, snapshot, mandate, clean)
    intent_event = custodian.ledger.read("req-1")[0]
    assert intent_event.observed["goal"].startswith("ingredients for a thai curry")
    assert [i["raw_text"] for i in intent_event.observed["requested"]] == \
           ["coconut milk", "thai red curry paste"]


def test_taxonomy_placement_is_recorded_as_inference_not_observation(custodian, snapshot, mandate, clean):
    """Base and form are derived. Filing them under `observed` would be a lie."""
    run(custodian, snapshot, mandate, clean)
    intent_event = custodian.ledger.read("req-1")[0]
    assert "placements" in intent_event.inferred
    assert "placements" not in intent_event.observed


def test_the_decision_event_separates_claim_from_conclusion(custodian, snapshot, mandate, snapshot_lines=None):
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 2, price=9_900, satisfies="i1-r1"),)
    run(custodian, snapshot, mandate, lines)
    event = next(e for e in custodian.ledger.read("req-1")
                 if e.event_type is EventType.DECISION_MADE)
    assert event.observed["asserted_total_paise"] == 19_800     # what the agent claimed
    assert event.inferred["verified_total_paise"] == 39_800     # what Custodian derived


def test_the_chain_stays_intact_across_a_decision(custodian, snapshot, mandate, clean):
    run(custodian, snapshot, mandate, clean)
    assert verify_chain(custodian.ledger).ok


def test_one_catalog_is_stored_once_across_many_decisions(custodian, snapshot, mandate, clean):
    """Content addressing: seventy items are written once, not once per decision."""
    for index in range(4):
        run(custodian, snapshot, mandate, clean, request_id=f"req-{index}")

    # One snapshot, plus a distinct input and decision per request (each carries
    # its own request_id, so they do not dedupe — only the catalog does).
    assert len(custodian.store) == 1 + 4 + 4
    assert custodian.store.get(snapshot.digest())["merchant_id"] == "m1"


# --- replay ----------------------------------------------------------------

def test_a_decision_reproduces_exactly_from_the_ledger(custodian, snapshot, mandate, clean, tables):
    original = run(custodian, snapshot, mandate, clean)
    result = replay(custodian.ledger, custodian.store, "req-1", tables=tables)
    assert result.matched, str(result)
    assert result.recomputed.outcome is original.outcome


def test_replay_calls_no_model(custodian, snapshot, mandate, clean, tables, monkeypatch):
    """The reproducibility claim: an audit trail you cannot replay is decoration."""
    run(custodian, snapshot, mandate, clean)

    import custodian.gate.semantic as semantic_module

    def explode(*args, **kwargs):
        raise AssertionError("replay called a model")

    monkeypatch.setattr(semantic_module.ClaudeScorer, "score", explode)
    monkeypatch.setattr(semantic_module.RecordedScorer, "score", explode)
    assert replay(custodian.ledger, custodian.store, "req-1", tables=tables).matched


def test_every_outcome_reproduces(custodian, snapshot, mandate, clean, tables):
    run(custodian, snapshot, mandate, clean, request_id="approved")
    run(custodian, snapshot, mandate, clean + (a_line(snapshot, "l9", WOK, 1),), request_id="held")
    run(custodian, snapshot, mandate,
        (a_line(snapshot, "l1", COCONUT_MILK, 2, price=1, satisfies="i1-r1"),), request_id="rejected")

    results = replay_all(custodian.ledger, custodian.store, tables=tables)
    assert len(results) == 3
    assert all(r.matched for r in results), [str(r) for r in results]
    assert {r.recorded.outcome for r in results} == {Outcome.APPROVE, Outcome.HOLD, Outcome.REJECT}


def test_a_changed_lexicon_refuses_to_replay_rather_than_quietly_differing(
    custodian, snapshot, mandate, clean, tables
):
    """The tables are an input, so a different lexicon is a different decision."""
    run(custodian, snapshot, mandate, clean)
    drifted = SubstitutionTables(version="lex-v99+form-v1", base_scores=tables.base_scores,
                                 form_scores=tables.form_scores)
    result = replay(custodian.ledger, custodian.store, "req-1", tables=drifted)
    assert not result.matched
    assert "lexicon version differs" in result.error


def test_a_divergence_names_the_fields_that_moved(custodian, snapshot, mandate, clean, tables):
    """"It does not reproduce" is not useful. Which field, and from what to what."""
    run(custodian, snapshot, mandate, clean)
    event = next(e for e in custodian.ledger.read("req-1")
                 if e.event_type is EventType.DECISION_MADE)
    tampered = dict(custodian.store.get(event.inferred["decision_digest"]), alignment_bp=1234)
    forged_digest = custodian.store.put(tampered, kind="decision")

    # Point a fresh request at the tampered decision, leaving the chain untouched.
    custodian.ledger.append(
        EventType.DECISION_MADE, "req-tampered",
        observed=dict(event.observed),
        inferred=dict(event.inferred, decision_digest=forged_digest),
    )
    result = replay(custodian.ledger, custodian.store, "req-tampered", tables=tables)
    assert not result.matched
    assert any("alignment_bp" in d for d in result.differences)


def test_replaying_something_that_was_never_decided_is_reported(custodian, tables):
    result = replay(custodian.ledger, custodian.store, "never-seen", tables=tables)
    assert not result.matched and "no decision recorded" in result.error


# --- escalation and the model's place --------------------------------------

@pytest.fixture
def escalating(snapshot, mandate):
    intent = an_intent(items=[{"raw_text": "whole turmeric", "quantity": 1}])
    return intent, (a_line(snapshot, "l1", TURMERIC, 1, satisfies="i1-r1"),)


def test_an_escalated_line_is_asked_about_and_the_answer_recorded(
    custodian, snapshot, mandate, escalating
):
    intent, lines = escalating
    scorer = RecordedScorer()
    scorer.record(intent.goal, intent.requested_items[0], snapshot.find(TURMERIC),
                  {"label": "FAITHFUL", "score_bp": 8_800, "rationale": "ground works here"})
    custodian.scorer = scorer

    decision = run(custodian, snapshot, mandate, lines, intent=intent)
    verdict_events = [e for e in custodian.ledger.read("req-1")
                      if e.event_type is EventType.SEMANTIC_VERDICT]
    assert len(verdict_events) == 1
    assert verdict_events[0].observed["raw_response"]          # what came back
    assert verdict_events[0].inferred["label"] == "FAITHFUL"   # what we read it as
    assert decision.outcome is Outcome.APPROVE


def test_a_rejected_cart_costs_no_tokens(custodian, snapshot, mandate, escalating):
    """The semantic scorer never sees a case the arithmetic already settled."""
    intent, _ = escalating
    forged = (a_line(snapshot, "l1", TURMERIC, 1, price=1, satisfies="i1-r1"),)

    class Exploding:
        model = "must-not-be-called"

        def score(self, **kwargs):
            raise AssertionError("a rejected cart called the model")

    custodian.scorer = Exploding()
    assert run(custodian, snapshot, mandate, forged, intent=intent).outcome is Outcome.REJECT


def test_a_scorer_failure_holds_rather_than_passing(custodian, snapshot, mandate, escalating):
    """A model that errors is not a verdict of 'fine'."""
    intent, lines = escalating

    class Broken:
        model = "broken"

        def score(self, **kwargs):
            raise ScoringError("upstream timeout")

    custodian.scorer = Broken()
    decision = run(custodian, snapshot, mandate, lines, intent=intent)
    assert decision.outcome is Outcome.HOLD
    errors = [e for e in custodian.ledger.read("req-1")
              if e.event_type is EventType.SEMANTIC_VERDICT and "error" in e.observed]
    assert len(errors) == 1


def test_an_unsure_verdict_holds(custodian, snapshot, mandate, escalating):
    intent, lines = escalating
    scorer = RecordedScorer()
    scorer.record(intent.goal, intent.requested_items[0], snapshot.find(TURMERIC),
                  {"label": "UNSURE", "score_bp": 5_000, "rationale": "depends on the dish"})
    custodian.scorer = scorer
    assert run(custodian, snapshot, mandate, lines, intent=intent).outcome is Outcome.HOLD


def test_the_scorer_satisfies_its_protocol():
    assert isinstance(RecordedScorer(), SemanticScorer)


# --- re-confirmation -------------------------------------------------------

def test_a_held_order_may_not_settle_until_someone_confirms(custodian, snapshot, mandate, clean):
    run(custodian, snapshot, mandate, clean + (a_line(snapshot, "l9", WOK, 1),))
    before = custodian.settlement_authority("req-1")
    assert not before.allowed and before.basis == "HELD"

    custodian.reconfirm("req-1", actor="anshul@kiit.ac.in", note="yes, I want the wok")
    after = custodian.settlement_authority("req-1")
    assert after.allowed and after.basis == "RECONFIRMED"
    assert "anshul@kiit.ac.in" in after.reason


def test_reconfirmation_does_not_rewrite_the_decision(custodian, snapshot, mandate, clean):
    """'Held, then a human overrode it' is the truthful entry."""
    decision = run(custodian, snapshot, mandate, clean + (a_line(snapshot, "l9", WOK, 1),))
    custodian.reconfirm("req-1", actor="anshul@kiit.ac.in")
    event = next(e for e in custodian.ledger.read("req-1")
                 if e.event_type is EventType.DECISION_MADE)
    assert decision.outcome is Outcome.HOLD
    assert event.inferred["outcome"] == "HOLD"


def test_a_rejection_cannot_be_confirmed_past(custodian, snapshot, mandate):
    """A hard constraint a human can wave through is advisory."""
    run(custodian, snapshot, mandate,
        (a_line(snapshot, "l1", COCONUT_MILK, 2, price=1, satisfies="i1-r1"),))
    with pytest.raises(PermissionError, match="cannot be re-confirmed"):
        custodian.reconfirm("req-1", actor="anshul@kiit.ac.in", note="override")
    assert not custodian.settlement_authority("req-1").allowed


def test_an_approved_order_needs_no_confirmation(custodian, snapshot, mandate, clean):
    run(custodian, snapshot, mandate, clean)
    authority = custodian.settlement_authority("req-1")
    assert authority.allowed and authority.basis == "APPROVED"


def test_confirming_something_that_was_never_decided_is_refused(custodian):
    with pytest.raises(PermissionError, match="no decision"):
        custodian.reconfirm("never-seen", actor="anshul@kiit.ac.in")


def test_the_authorised_amount_is_the_verified_total(custodian, snapshot, mandate):
    """What settles is what Custodian derived, even after a human confirms."""
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 2, price=9_900, satisfies="i1-r1"),
             a_line(snapshot, "l9", WOK, 1))
    run(custodian, snapshot, mandate, lines)
    assert custodian.settlement_authority("req-1").amount_paise == 39_800 + 145_000
