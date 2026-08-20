"""The data contracts. These are the trust boundary, so the tests attack them."""

import pytest
from pydantic import ValidationError

from custodian.gate.reasons import BLOCKING, EXPLANATION, ReasonCode
from custodian.gate.thresholds import DEFAULT, Thresholds
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.catalog import UNKNOWN, CatalogItem, CatalogSnapshot, Sanitization, SanitizerFlag
from custodian.schemas.decision import (
    Binding, BindingKind, Decision, Dimension, DimensionResult, DimensionStatus, Outcome,
)
from custodian.schemas.decision_input import DecisionInput
from custodian.schemas.intent import Intent, RequestedItem, SubstitutionPolicy
from custodian.schemas.mandate import Mandate
from custodian.schemas.verdict import SemanticVerdict, VerdictLabel

NOW = "2026-08-22T00:00:00+00:00"


def item(**over) -> CatalogItem:
    return CatalogItem(**{
        "item_id": "cat-coconut-milk", "name": "Coconut Milk 400ml",
        "raw_name": "dabur coconut milk 400 ml ₹199", "price_paise": 19_900, "in_stock": True,
        "base": "coconut", "form": "milk", "category": "dairy-alt",
        "unit_quantity": 400, "unit": "ml", **over})


def snapshot(*items_, **over) -> CatalogSnapshot:
    return CatalogSnapshot(**{
        "snapshot_id": "snap-1", "merchant_id": "m1", "taken_at": NOW,
        "items": items_ or (item(),), "lexicon_version": "lex-v1", **over})


def mandate(**over) -> Mandate:
    return Mandate(**{
        "mandate_id": "mnd-1", "max_amount_paise": 500_000, "per_transaction_cap_paise": 200_000,
        "valid_from": "2026-08-01T00:00:00+00:00", "valid_until": "2026-09-01T00:00:00+00:00",
        "merchant_allowlist": ("m1",), **over})


def intent(**over) -> Intent:
    return Intent(**{
        "intent_id": "int-1", "goal": "ingredients for a thai curry, under ₹2,000",
        "budget_paise": 200_000, "merchant_scope": ("m1",),
        "requested_items": (RequestedItem(line_id="r1", raw_text="coconut milk",
                                          base="coconut", form="milk", category="dairy-alt"),),
        **over})


def cart(**over) -> Cart:
    return Cart(**{
        "cart_id": "crt-1", "merchant_id": "m1",
        "lines": (CartLine(line_id="l1", item_id="cat-coconut-milk", name_asserted="Coconut Milk 400ml",
                           quantity=2, asserted_unit_price_paise=19_900, satisfies_line_id="r1"),),
        **over})


# --- the boundary controls -------------------------------------------------

def test_a_float_price_cannot_cross_the_boundary():
    """Pydantic's default would coerce 199.0 to 199 silently. See ADR-001."""
    with pytest.raises(ValidationError):
        item(price_paise=19_900.0)


def test_an_untrusted_client_cannot_smuggle_extra_fields():
    with pytest.raises(ValidationError, match="hidden_flag"):
        item(hidden_flag=True)


def test_evidence_cannot_be_mutated_after_it_is_built():
    with pytest.raises(ValidationError):
        item().price_paise = 1


def test_a_bool_is_not_a_quantity():
    with pytest.raises(ValidationError):
        CartLine(line_id="l", item_id="i", name_asserted="x", quantity=True,
                 asserted_unit_price_paise=1)


# --- catalog ---------------------------------------------------------------

def test_snapshot_digest_depends_only_on_content():
    assert snapshot().digest() == snapshot().digest()
    assert snapshot().digest() != snapshot(item(price_paise=20_000)).digest()


def test_snapshot_refuses_duplicate_item_ids():
    with pytest.raises(ValidationError, match="duplicate item_id"):
        snapshot(item(), item())


def test_unit_and_quantity_are_all_or_nothing():
    with pytest.raises(ValidationError, match="together"):
        item(unit=None)


def test_an_unplaced_item_is_marked_unresolved_not_guessed():
    assert not item(base=UNKNOWN).resolved
    assert item().resolved


def test_a_missing_item_returns_none_rather_than_raising():
    assert snapshot().find("nope") is None


def test_sanitizer_findings_keep_the_evidence():
    s = Sanitization(flags=(SanitizerFlag.INSTRUCTION_LIKE,),
                     flagged_spans=("ignore previous instructions",))
    assert not s.clean and s.flagged_spans


# --- intent, cart, mandate -------------------------------------------------

def test_an_intent_must_ask_for_something():
    with pytest.raises(ValidationError, match="cannot be satisfied or violated"):
        intent(requested_items=())


def test_an_empty_cart_has_nothing_to_verify():
    with pytest.raises(ValidationError, match="nothing to verify"):
        cart(lines=())


def test_the_agents_total_is_named_as_a_claim():
    """A field called `price` invites trusting it. Every price here says whose it is."""
    assert cart().asserted_total_paise == 39_800
    priced = [f for f in CartLine.model_fields if "price" in f]
    assert priced == ["asserted_unit_price_paise"]
    assert all(f.startswith("asserted_") for f in priced)


def test_default_substitution_policy_is_the_conservative_one():
    assert intent().substitution_policy is SubstitutionPolicy.SAME_BASE


def test_a_mandate_cap_cannot_exceed_its_envelope():
    with pytest.raises(ValidationError, match="exceeds"):
        mandate(per_transaction_cap_paise=600_000)


def test_a_mandate_authorising_nobody_is_not_a_mandate():
    with pytest.raises(ValidationError, match="authorises nothing"):
        mandate(merchant_allowlist=())


def test_a_mandate_window_must_be_ordered():
    with pytest.raises(ValidationError, match="ends before it starts"):
        mandate(valid_from="2026-09-01T00:00:00+00:00", valid_until="2026-08-01T00:00:00+00:00")


@pytest.mark.parametrize("moment,active", [
    ("2026-07-31T23:59:59+00:00", False),
    ("2026-08-01T00:00:00+00:00", True),   # inclusive start
    ("2026-08-31T23:59:59+00:00", True),
    ("2026-09-01T00:00:00+00:00", False),  # exclusive end
])
def test_mandate_window_is_half_open(moment, active):
    assert mandate().active_at(moment) is active


def test_a_revoked_mandate_is_never_active():
    assert not mandate(revoked=True).active_at(NOW)


def test_mandate_timestamps_must_use_the_one_spelling():
    with pytest.raises(ValidationError):
        mandate(valid_from="2026-08-01T00:00:00+05:30")


# --- thresholds ------------------------------------------------------------

def test_the_hold_band_must_have_room_in_it():
    with pytest.raises(ValidationError, match="no room to hold"):
        Thresholds(version="x", approve_min_alignment_bp=4_000, reject_max_alignment_bp=5_000)


def test_substitution_bands_must_leave_something_to_escalate():
    with pytest.raises(ValidationError, match="nothing could escalate"):
        Thresholds(version="x", substitution_faithful_bp=4_000, substitution_unfaithful_bp=8_000)


def test_price_tolerance_is_zero_because_a_price_is_looked_up_not_estimated():
    assert DEFAULT.price_tolerance_paise == 0


def test_thresholds_digest_changes_when_a_dial_moves():
    assert DEFAULT.digest() != DEFAULT.model_copy(update={"min_confidence_bp": 7_500}).digest()


# --- reason codes ----------------------------------------------------------

def test_every_reason_code_can_be_explained_to_a_merchant():
    assert not [c for c in ReasonCode if c not in EXPLANATION]


def test_blocking_codes_are_a_subset_of_all_codes():
    assert BLOCKING <= set(ReasonCode)


# --- decision --------------------------------------------------------------

def _dims(**over) -> tuple[DimensionResult, ...]:
    base = {d: (DimensionStatus.PASS, 10_000, (ReasonCode.SCOPE_CLEAN,)) for d in Dimension}
    base.update(over)
    return tuple(DimensionResult(dimension=d, status=s, score_bp=v, reason_codes=r)
                 for d, (s, v, r) in base.items())


def decision(**over) -> Decision:
    return Decision(**{
        "request_id": "req-1", "outcome": Outcome.APPROVE, "evaluated_at": NOW,
        "alignment_bp": 9_500, "confidence_bp": 9_200, "dimensions": _dims(), "bindings": (),
        "verified_total_paise": 39_800, "snapshot_digest": "a" * 64,
        "thresholds_version": "v0", "thresholds_digest": "b" * 64, **over})


def test_approval_carrying_a_blocking_violation_is_unconstructable():
    """The property test the type system enforces: over-mandate cannot approve."""
    over = {Dimension.MANDATE: (DimensionStatus.FAIL, 0, (ReasonCode.MANDATE_PER_TXN_EXCEEDED,))}
    with pytest.raises(ValidationError, match="unconstructable"):
        decision(dimensions=_dims(**over))
    assert decision(outcome=Outcome.REJECT, dimensions=_dims(**over)).outcome is Outcome.REJECT


def test_a_decision_must_report_every_dimension():
    with pytest.raises(ValidationError, match="missing"):
        decision(dimensions=_dims()[:4])


def test_a_dimension_cannot_be_scored_twice():
    with pytest.raises(ValidationError, match="scored twice"):
        decision(dimensions=_dims() + _dims()[:1])


def test_a_score_without_a_reason_is_not_explainable():
    with pytest.raises(ValidationError, match="no reason code"):
        DimensionResult(dimension=Dimension.BUDGET, status=DimensionStatus.PASS, score_bp=1, reason_codes=())


def test_a_refusal_must_give_the_merchant_something_to_act_on():
    with pytest.raises(ValidationError, match="nothing to act on"):
        decision(outcome=Outcome.HOLD)


def test_reason_text_is_rendered_from_codes_never_authored():
    over = {Dimension.SUBSTITUTION: (DimensionStatus.FAIL, 0, (ReasonCode.SUBST_BASE_CHANGED,))}
    d = decision(outcome=Outcome.REJECT, dimensions=_dims(**over))
    assert d.reason_text == EXPLANATION[ReasonCode.SUBST_BASE_CHANGED]


def test_a_clean_approval_still_says_something():
    assert decision().reason_text == "Every check passed."


@pytest.mark.parametrize("kind,line", [
    (BindingKind.UNBOUND, "r1"),        # unbound but names a request line
    (BindingKind.SUBSTITUTION, None),   # bound but names nothing
])
def test_binding_kind_must_agree_with_what_it_points_at(kind, line):
    with pytest.raises(ValidationError, match="disagrees"):
        Binding(cart_line_id="l1", requested_line_id=line, kind=kind, score_bp=5_000,
                reason_codes=(ReasonCode.SCOPE_CLEAN,))


def test_the_unrequested_wok_is_representable():
    """Within budget, out of scope — the case a budget check alone misses."""
    b = Binding(cart_line_id="l9", requested_line_id=None, kind=BindingKind.UNBOUND,
                score_bp=0, reason_codes=(ReasonCode.SCOPE_UNREQUESTED_ITEM,))
    assert b.requested_line_id is None


# --- decision input --------------------------------------------------------

def decision_input(**over) -> DecisionInput:
    return DecisionInput(**{
        "request_id": "req-1", "evaluated_at": NOW, "intent": intent(), "cart": cart(),
        "snapshot": snapshot(), "mandate": mandate(), "thresholds": DEFAULT, **over})


def test_the_whole_input_hashes_stably():
    assert decision_input().digest() == decision_input().digest()


def test_changing_any_input_changes_the_digest():
    assert decision_input().digest() != decision_input(intent=intent(budget_paise=100_000)).digest()


def test_a_recorded_verdict_is_retrievable_by_cart_line():
    v = SemanticVerdict(cart_line_id="l1", requested_line_id="r1", label=VerdictLabel.FAITHFUL,
                        score_bp=8_800, model="claude-sonnet-5", prompt_digest="c" * 64,
                        raw_response='{"label":"FAITHFUL"}', obtained_at=NOW)
    inp = decision_input(semantic_verdicts=(v,))
    assert inp.verdict_for("l1") is v
    assert inp.verdict_for("l-none") is None


def test_unsure_is_available_so_the_model_has_somewhere_honest_to_go():
    v = SemanticVerdict(cart_line_id="l1", requested_line_id="r1", label=VerdictLabel.UNSURE,
                        score_bp=5_000, model="claude-sonnet-5", prompt_digest="c" * 64,
                        raw_response='{"label":"UNSURE"}', obtained_at=NOW)
    assert not v.usable


def test_the_decision_input_carries_no_clock():
    """If it is not on this object, decide() cannot use it. See ADR-010."""
    assert "evaluated_at" in DecisionInput.model_fields
