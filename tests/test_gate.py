"""The gate. The one component that is not plumbing."""

import pytest

from custodian import bp
from custodian.canonical import canonical_hash
from custodian.gate.decide import decide, escalations
from custodian.gate.reasons import BLOCKING, ReasonCode
from custodian.gate.substitution import SubstitutionTables, assess
from custodian.gate.thresholds import DEFAULT, Thresholds
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent.parser import resolve
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.catalog import UNKNOWN, CatalogItem
from custodian.schemas.decision import Dimension, DimensionStatus, Outcome
from custodian.schemas.decision_input import DecisionInput
from custodian.schemas.intent import RequestedItem, SubstitutionPolicy
from custodian.schemas.mandate import Mandate
from custodian.schemas.verdict import SemanticVerdict, VerdictLabel

NOW = "2026-08-26T09:00:00+00:00"

# Catalog ids used throughout, so a test reads as a scenario rather than a lookup.
COCONUT_MILK, COCONUT_CREAM, ALMOND_MILK = "SKU001", "SKU002", "SKU003"
CURRY_PASTE, LEMONGRASS, TURMERIC, WOK = "SKU055", "SKU053", "SKU032", "SKU068"


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


def an_intent(*, policy="SAME_BASE", budget=200_000, items=None, merchants=("m1",), categories=None):
    payload = {
        "goal": "ingredients for a thai curry, under Rs 2000",
        "budget_paise": budget, "merchant_scope": list(merchants),
        "substitution_policy": policy,
        "requested_items": items or [
            {"raw_text": "coconut milk", "quantity": 2},
            {"raw_text": "thai red curry paste", "quantity": 1},
            {"raw_text": "lemongrass", "quantity": 1},
        ],
    }
    if categories is not None:
        payload["category_scope"] = list(categories)
    return resolve(payload, intent_id="i1")


def a_line(snapshot, line_id, item_id, quantity=1, price=None, satisfies=None):
    item = snapshot.find(item_id)
    return CartLine(line_id=line_id, item_id=item_id, name_asserted=item.name,
                    quantity=quantity,
                    asserted_unit_price_paise=item.price_paise if price is None else price,
                    satisfies_line_id=satisfies)


def an_input(snapshot, mandate, lines, *, intent=None, verdicts=(), thresholds=DEFAULT,
             evaluated_at=NOW, merchant="m1"):
    return DecisionInput(
        request_id="req-1", evaluated_at=evaluated_at, intent=intent or an_intent(),
        cart=Cart(cart_id="c1", merchant_id=merchant, lines=lines), snapshot=snapshot,
        mandate=mandate, semantic_verdicts=verdicts, thresholds=thresholds,
    )


@pytest.fixture
def clean(snapshot):
    return (a_line(snapshot, "l1", COCONUT_MILK, 2, satisfies="i1-r1"),
            a_line(snapshot, "l2", CURRY_PASTE, 1, satisfies="i1-r2"),
            a_line(snapshot, "l3", LEMONGRASS, 1, satisfies="i1-r3"))


# --- the flagship pair, decided without a model -----------------------------

def test_a_faithful_substitution_approves_deterministically(snapshot, mandate, tables, clean):
    """Coconut milk out of stock, coconut cream offered. Same base, listed form pair."""
    lines = (a_line(snapshot, "l1", COCONUT_CREAM, 2, satisfies="i1-r1"),) + clean[1:]
    inp = an_input(snapshot, mandate, lines)
    assert escalations(inp, tables=tables) == ()          # no model needed
    assert decide(inp, tables=tables).outcome is Outcome.APPROVE


def test_a_changed_base_rejects_deterministically(snapshot, mandate, tables, clean):
    """Almond milk for coconut milk. Lexical similarity cannot tell these apart."""
    lines = (a_line(snapshot, "l1", ALMOND_MILK, 2, satisfies="i1-r1"),) + clean[1:]
    inp = an_input(snapshot, mandate, lines)
    decision = decide(inp, tables=tables)
    assert escalations(inp, tables=tables) == ()
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.SUBST_BASE_UNRELATED in decision.dimension(Dimension.SUBSTITUTION).reason_codes


def test_both_flagship_cases_are_settled_by_arithmetic(snapshot, mandate, tables, clean):
    """The premise of ADR-007: the deterministic layer decides the hard example."""
    for item_id in (COCONUT_CREAM, ALMOND_MILK):
        lines = (a_line(snapshot, "l1", item_id, 2, satisfies="i1-r1"),) + clean[1:]
        assert escalations(an_input(snapshot, mandate, lines), tables=tables) == ()


# --- the three-way gate ----------------------------------------------------

def test_a_clean_order_approves(snapshot, mandate, tables, clean):
    decision = decide(an_input(snapshot, mandate, clean), tables=tables)
    assert decision.outcome is Outcome.APPROVE
    assert decision.alignment_bp == bp.FULL


def test_scope_creep_holds_rather_than_rejecting(snapshot, mandate, tables, clean):
    """The ₹1,450 wok: inside budget, correctly priced, in stock, not asked for.

    Held, not rejected — the human is the authority on whether they want it, and
    a system that only blocks is a system merchants switch off.
    """
    lines = clean + (a_line(snapshot, "l9", WOK, 1),)
    decision = decide(an_input(snapshot, mandate, lines, intent=an_intent(budget=300_000)),
                      tables=tables)
    assert decision.outcome is Outcome.HOLD
    scope = decision.dimension(Dimension.SCOPE_CREEP)
    assert scope.status is DimensionStatus.FAIL
    assert ReasonCode.SCOPE_UNREQUESTED_ITEM in scope.reason_codes


def test_a_failed_dimension_can_never_be_outvoted_by_a_good_average(snapshot, mandate, tables, clean):
    """The bug BROKE.md 007 records: the wok scored 32% and the order approved."""
    lines = clean + (a_line(snapshot, "l9", WOK, 1),)
    decision = decide(an_input(snapshot, mandate, lines, intent=an_intent(budget=300_000)),
                      tables=tables)
    assert decision.alignment_bp > DEFAULT.approve_min_alignment_bp  # the average still looks fine
    assert decision.outcome is not Outcome.APPROVE                   # and it still cannot approve


def test_uncertainty_routes_to_hold_never_to_a_guess(snapshot, mandate, tables):
    """Turmeric whole for turmeric powder: a real substitution nobody has judged."""
    intent = an_intent(items=[{"raw_text": "whole turmeric", "quantity": 1}])
    lines = (a_line(snapshot, "l1", TURMERIC, 1, satisfies="i1-r1"),)
    inp = an_input(snapshot, mandate, lines, intent=intent)
    assert escalations(inp, tables=tables) == ("l1",)
    assert decide(inp, tables=tables).outcome is Outcome.HOLD


# --- deterministic checks reject on their own authority ---------------------

def test_a_forged_price_rejects(snapshot, mandate, tables, clean):
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 2, price=9_900, satisfies="i1-r1"),) + clean[1:]
    decision = decide(an_input(snapshot, mandate, lines), tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.PRICE_MISMATCH in decision.dimension(Dimension.PRICE_INTEGRITY).reason_codes


def test_the_charged_amount_is_the_catalogs_not_the_agents(snapshot, mandate, tables, clean):
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 2, price=9_900, satisfies="i1-r1"),) + clean[1:]
    inp = an_input(snapshot, mandate, lines)
    assert inp.cart.asserted_total_paise == 49_800
    assert decide(inp, tables=tables).verified_total_paise == 69_800


def test_over_budget_rejects(snapshot, mandate, tables, clean):
    decision = decide(an_input(snapshot, mandate, clean, intent=an_intent(budget=50_000)),
                      tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.BUDGET_EXCEEDED in decision.dimension(Dimension.BUDGET).reason_codes


def test_a_merchant_the_human_never_named_rejects(snapshot, mandate, tables, clean):
    intent = an_intent(merchants=("some-other-shop",))
    decision = decide(an_input(snapshot, mandate, clean, intent=intent), tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.MERCHANT_OUT_OF_SCOPE in decision.dimension(Dimension.MERCHANT_SCOPE).reason_codes


def test_a_revoked_mandate_rejects(snapshot, mandate, tables, clean):
    revoked = mandate.model_copy(update={"revoked": True})
    decision = decide(an_input(snapshot, revoked, clean), tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.MANDATE_REVOKED in decision.dimension(Dimension.MANDATE).reason_codes


def test_an_expired_mandate_rejects(snapshot, mandate, tables, clean):
    expired = mandate.model_copy(update={"valid_until": "2026-08-02T00:00:00+00:00"})
    decision = decide(an_input(snapshot, expired, clean), tables=tables)
    assert ReasonCode.MANDATE_EXPIRED in decision.dimension(Dimension.MANDATE).reason_codes


def test_over_the_per_transaction_cap_rejects(snapshot, mandate, tables, clean):
    capped = mandate.model_copy(update={"per_transaction_cap_paise": 10_000})
    decision = decide(an_input(snapshot, capped, clean), tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.MANDATE_PER_TXN_EXCEEDED in decision.dimension(Dimension.MANDATE).reason_codes


def test_a_stale_snapshot_rejects(snapshot, mandate, tables, clean):
    """Prices change. A decision made against yesterday's catalog is not a decision."""
    decision = decide(an_input(snapshot, mandate, clean, evaluated_at="2026-08-27T09:00:00+00:00"),
                      tables=tables)
    assert ReasonCode.SNAPSHOT_STALE in decision.dimension(Dimension.PRICE_INTEGRITY).reason_codes


def test_an_item_outside_the_stated_categories_rejects(snapshot, mandate, tables, clean):
    intent = an_intent(categories=("dairy-alt",))
    decision = decide(an_input(snapshot, mandate, clean, intent=intent), tables=tables)
    assert ReasonCode.CATEGORY_OUT_OF_SCOPE in decision.dimension(Dimension.CATEGORY_SCOPE).reason_codes


def test_quantity_inflation_is_scope_creep_wearing_a_different_shape(snapshot, mandate, tables, clean):
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 6, satisfies="i1-r1"),) + clean[1:]
    decision = decide(an_input(snapshot, mandate, lines), tables=tables)
    assert ReasonCode.SCOPE_QUANTITY_INFLATED in decision.dimension(Dimension.SCOPE_CREEP).reason_codes
    assert decision.outcome is not Outcome.APPROVE


# --- the human's policy is not the gate's opinion ---------------------------

def test_exact_only_refuses_a_substitution_the_gate_scores_highly(snapshot, mandate, tables, clean):
    """Coconut cream scores 8500 and is still refused, because the human said no."""
    lines = (a_line(snapshot, "l1", COCONUT_CREAM, 2, satisfies="i1-r1"),) + clean[1:]
    intent = an_intent(policy="EXACT_ONLY")
    decision = decide(an_input(snapshot, mandate, lines, intent=intent), tables=tables)
    assert decision.outcome is Outcome.REJECT
    assert ReasonCode.SUBST_POLICY_FORBIDS in decision.dimension(Dimension.SUBSTITUTION).reason_codes


def test_same_base_refuses_a_permitted_equivalence(snapshot, mandate, tables):
    """Sunflower for groundnut oil is a listed equivalence, and SAME_BASE still forbids it."""
    intent = an_intent(items=[{"raw_text": "sunflower oil", "quantity": 1}], policy="SAME_BASE")
    lines = (a_line(snapshot, "l1", "SKU029", 1, satisfies="i1-r1"),)  # groundnut oil
    decision = decide(an_input(snapshot, mandate, lines, intent=intent), tables=tables)
    assert decision.outcome is Outcome.REJECT

    permissive = an_intent(items=[{"raw_text": "sunflower oil", "quantity": 1}], policy="EQUIVALENT")
    assert decide(an_input(snapshot, mandate, lines, intent=permissive),
                  tables=tables).outcome is not Outcome.REJECT


# --- the model's place ------------------------------------------------------

def _verdict(label, score, line_id="l1", requested="i1-r1"):
    return SemanticVerdict(cart_line_id=line_id, requested_line_id=requested, label=label,
                           score_bp=score, model="claude-opus-5", prompt_digest="a" * 64,
                           raw_response='{"label":"' + str(label) + '"}', obtained_at=NOW)


@pytest.fixture
def escalating(snapshot, mandate):
    intent = an_intent(items=[{"raw_text": "whole turmeric", "quantity": 1}])
    lines = (a_line(snapshot, "l1", TURMERIC, 1, satisfies="i1-r1"),)
    return lambda verdicts=(): an_input(snapshot, mandate, lines, intent=intent, verdicts=verdicts)


def test_a_faithful_verdict_resolves_an_escalation(escalating, tables):
    decision = decide(escalating((_verdict(VerdictLabel.FAITHFUL, 9_000),)), tables=tables)
    assert decision.outcome is Outcome.APPROVE
    assert ReasonCode.SUBST_MODEL_FAITHFUL in decision.dimension(Dimension.SUBSTITUTION).reason_codes


def test_an_unfaithful_verdict_does_not_approve(escalating, tables):
    decision = decide(escalating((_verdict(VerdictLabel.UNFAITHFUL, 2_000),)), tables=tables)
    assert decision.outcome is not Outcome.APPROVE


def test_an_unsure_verdict_lowers_confidence_furthest(escalating, tables):
    """The model saying it does not know is weaker evidence than never asking."""
    unsure = decide(escalating((_verdict(VerdictLabel.UNSURE, 5_000),)), tables=tables)
    unasked = decide(escalating(), tables=tables)
    assert unsure.outcome is Outcome.HOLD
    assert unsure.confidence_bp < unasked.confidence_bp


def test_a_missing_verdict_holds_rather_than_assuming(escalating, tables):
    decision = decide(escalating(), tables=tables)
    assert decision.outcome is Outcome.HOLD
    assert ReasonCode.SUBST_VERDICT_MISSING in decision.dimension(Dimension.SUBSTITUTION).reason_codes


def test_confidence_is_computed_not_reported_by_the_model(escalating, tables):
    """A verdict claiming certainty cannot manufacture confidence in the gate."""
    overconfident = decide(escalating((_verdict(VerdictLabel.FAITHFUL, 10_000),)), tables=tables)
    assert overconfident.confidence_bp < bp.FULL


def test_the_semantic_scorer_never_sees_a_case_the_arithmetic_settled(snapshot, mandate, tables):
    """A rejected cart costs no tokens. The cost argument, implemented."""
    intent = an_intent(items=[{"raw_text": "whole turmeric", "quantity": 1}])
    forged = (a_line(snapshot, "l1", TURMERIC, 1, price=1, satisfies="i1-r1"),)
    inp = an_input(snapshot, mandate, forged, intent=intent)
    assert escalations(inp, tables=tables) == ()
    assert decide(inp, tables=tables).outcome is Outcome.REJECT


# --- purity, which the replay claim rests on --------------------------------

def test_the_same_input_produces_the_same_bytes(snapshot, mandate, tables, clean):
    inp = an_input(snapshot, mandate, clean)
    assert canonical_hash(decide(inp, tables=tables).canonical()) == \
           canonical_hash(decide(inp, tables=tables).canonical())


def test_input_key_order_does_not_change_the_decision(snapshot, mandate, tables, clean):
    inp = an_input(snapshot, mandate, clean)
    shuffled = DecisionInput.model_validate(dict(reversed(list(inp.model_dump().items()))))
    assert canonical_hash(decide(shuffled, tables=tables).canonical()) == \
           canonical_hash(decide(inp, tables=tables).canonical())


def test_decide_reads_no_clock(snapshot, mandate, tables, clean):
    """Staleness is a comparison between two recorded values, never a clock read."""
    inp = an_input(snapshot, mandate, clean)
    assert decide(inp, tables=tables).evaluated_at == inp.evaluated_at


def test_decide_touches_no_model_client(snapshot, mandate, tables, clean, monkeypatch):
    import custodian.intent.claude as claude_module

    def explode(*args, **kwargs):
        raise AssertionError("decide() called a model")

    monkeypatch.setattr(claude_module.ClaudeParser, "parse", explode)
    assert decide(an_input(snapshot, mandate, clean), tables=tables).outcome is Outcome.APPROVE


def test_every_decision_names_what_it_was_derived_from(snapshot, mandate, tables, clean):
    decision = decide(an_input(snapshot, mandate, clean), tables=tables)
    assert decision.snapshot_digest == snapshot.digest()
    assert decision.thresholds_digest == DEFAULT.digest()
    assert decision.thresholds_version == DEFAULT.version


# --- thresholds are a dial, which is what the sweep will turn ---------------

def test_moving_the_approve_threshold_changes_the_outcome(snapshot, mandate, tables, clean):
    lines = (a_line(snapshot, "l1", COCONUT_CREAM, 2, satisfies="i1-r1"),) + clean[1:]
    strict = Thresholds(version="strict", approve_min_alignment_bp=9_900,
                        reject_max_alignment_bp=4_000)
    assert decide(an_input(snapshot, mandate, lines), tables=tables).outcome is Outcome.APPROVE
    assert decide(an_input(snapshot, mandate, lines, thresholds=strict),
                  tables=tables).outcome is Outcome.HOLD


def test_blocking_codes_reject_regardless_of_threshold(snapshot, mandate, tables, clean):
    """A hard constraint is not a dial."""
    permissive = Thresholds(version="permissive", approve_min_alignment_bp=100,
                            reject_max_alignment_bp=1, min_confidence_bp=0)
    lines = (a_line(snapshot, "l1", COCONUT_MILK, 2, price=1, satisfies="i1-r1"),) + clean[1:]
    assert decide(an_input(snapshot, mandate, lines, thresholds=permissive),
                  tables=tables).outcome is Outcome.REJECT


# --- substitution scoring ---------------------------------------------------

def _req(base, form, category="dairy-alt"):
    return RequestedItem(line_id="r1", raw_text="x", base=base, form=form, category=category)


def _item(base, form, category="dairy-alt"):
    return CatalogItem(item_id="i1", name="n", raw_name="n", price_paise=1, in_stock=True,
                       base=base, form=form, category=category)


def test_the_weakest_attribute_governs(tables):
    """A perfect base cannot carry an incompatible form past the threshold."""
    result = assess(_req("coconut", "milk"), _item("coconut", "flour"),
                    policy=SubstitutionPolicy.SAME_BASE, tables=tables, thresholds=DEFAULT)
    assert result.score_bp <= 10_000 and result.needs_escalation or result.score_bp < 10_000


def test_an_unknown_attribute_escalates_rather_than_failing(tables):
    result = assess(_req(UNKNOWN, "milk"), _item("coconut", "milk"),
                    policy=SubstitutionPolicy.SAME_BASE, tables=tables, thresholds=DEFAULT)
    assert result.needs_escalation and not result.blocked


def test_a_permitted_equivalence_is_not_a_blocking_code(tables):
    """SUBST_BASE_CHANGED fires for legitimate swaps and must not reject them."""
    assert ReasonCode.SUBST_BASE_CHANGED not in BLOCKING
    assert ReasonCode.SUBST_BASE_UNRELATED in BLOCKING
