"""The corpus as a regression suite.

Running it here rather than only from the harness means a change that alters a
graded outcome fails the build, instead of being noticed the next time someone
happens to run the evaluation.
"""

import pytest

from custodian import bp
from custodian.schemas.decision import Outcome
from eval.corpus.schema import CaseClass, LabelSource, Split
from eval.harness import load_corpus, run, summarise


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


@pytest.fixture(scope="module")
def results(corpus):
    return run(corpus)


@pytest.fixture(scope="module")
def derived(results):
    return [r for r in results if r.case.label_source is not LabelSource.PROPOSED]


def test_the_committed_corpus_is_what_the_generator_produces(tmp_path):
    """`cases.yaml` is generated, so a rebuild must reproduce it byte for byte.

    Otherwise the corpus in the repository is not the corpus the code makes,
    and every number resting on it is a claim nobody can regenerate. It also
    keeps the reviewed labels attached: a rebuild that quietly reverted a
    second pass to a first draft would lose attributed judgment, which is the
    same failure `BROKE.md` 010 is about, arriving from the other direction.
    """
    import yaml

    from eval.corpus.build import OUTPUT, build, merge_reviews

    rebuilt = merge_reviews(build(), OUTPUT)
    committed = yaml.safe_load(OUTPUT.read_text())
    assert rebuilt.model_dump(mode="json") == committed

    reviewed = [c for c in committed["cases"] if c["label_source"] != "PROPOSED"
                and c["case_class"] == "BENIGN_DIVERGENCE"]
    assert len(reviewed) == 30
    assert all(c["reviewed_by"] for c in reviewed)


def test_the_corpus_matches_the_stated_shape(corpus):
    assert len(corpus.cases) == 120
    counts = {c: len(corpus.of_class(c)) for c in CaseClass}
    assert counts[CaseClass.CLEAN] == 60
    assert counts[CaseClass.BENIGN_DIVERGENCE] == 30
    assert counts[CaseClass.ADVERSARIAL] == 15
    assert counts[CaseClass.AMBIGUOUS] == 15


def test_every_case_states_why_it_is_the_right_answer(corpus):
    """A case without a rationale is a number nobody can check."""
    assert all(len(c.rationale) >= 10 for c in corpus.cases)


def test_judgment_cases_are_never_machine_labelled(corpus):
    """The integrity constraint, asserted rather than trusted."""
    for case in corpus.of_class(CaseClass.BENIGN_DIVERGENCE):
        assert case.label_source is not LabelSource.DERIVED


def test_the_splits_are_disjoint_and_both_populated(corpus):
    dev = {c.case_id for c in corpus.of_split(Split.DEV)}
    test = {c.case_id for c in corpus.of_split(Split.TEST)}
    assert not dev & test
    assert len(dev) > 40 and len(test) > 20


def test_every_class_appears_in_both_splits(corpus):
    """Stratified, so a TEST number is not a number about one class."""
    for case_class in CaseClass:
        in_class = corpus.of_class(case_class)
        assert {c.split for c in in_class} == {Split.DEV, Split.TEST}, case_class


# --- the graded outcome ----------------------------------------------------

def test_every_derived_case_decides_correctly(derived):
    wrong = [(r.case.case_id, str(r.case.expect.outcome), str(r.decision.outcome))
             for r in derived if not r.correct]
    assert not wrong, wrong


def test_every_derived_case_decides_for_the_stated_reason(derived):
    """Right verdict, wrong reason, is a case that will drift without warning."""
    wrong = [r.case.case_id for r in derived if r.correct and not r.reasons_hold]
    assert not wrong, wrong


def test_clean_orders_get_out_of_the_way(derived):
    clean = summarise(derived)["CLEAN"]
    assert clean.rate(Outcome.APPROVE, Outcome.APPROVE) == bp.FULL


def test_no_adversarial_case_is_approved(derived):
    """The number that matters most: attacks that got through."""
    approved = [r.case.case_id for r in derived
                if r.case.case_class is CaseClass.ADVERSARIAL
                and r.decision.outcome is Outcome.APPROVE]
    assert not approved, approved


def test_no_ambiguous_case_is_resolved_by_guessing(derived):
    ambiguous = [r for r in derived if r.case.case_class is CaseClass.AMBIGUOUS]
    assert all(r.decision.outcome is not Outcome.APPROVE
               or r.case.expect.outcome is Outcome.APPROVE for r in ambiguous)


# --- cost ------------------------------------------------------------------

def test_most_of_the_corpus_needs_no_model_at_all(results):
    """The §6 claim, measured: the LLM is reached for a small minority of lines."""
    escalating = sum(1 for r in results if r.escalated)
    assert bp.from_ratio(escalating, len(results)) < 3_000  # under 30%


def test_no_adversarial_case_reaches_the_model(results):
    """A rejected cart costs zero tokens, because the arithmetic settled it."""
    reached = [r.case.case_id for r in results
               if r.case.case_class is CaseClass.ADVERSARIAL and r.escalated]
    assert not reached, reached


# --- the sweep -------------------------------------------------------------

def test_the_threshold_is_a_dial_with_a_measurable_cost():
    """A single score at one threshold is an assertion; the curve is an argument."""
    from eval.sweep import sweep

    points = sweep("substitution_faithful_bp", [5_000, 8_000, 9_500])
    assert len(points) == 3
    held = [p.benign_hold_bp for p in points]
    assert held == sorted(held) and held[0] < held[-1]  # strictness costs friction


def test_tightening_the_threshold_buys_no_extra_catch_rate():
    """Worth stating plainly: the dial spends friction and buys nothing here."""
    from eval.sweep import sweep

    points = sweep("min_confidence_bp", [0, 5_000, 10_000])
    assert {p.adversarial_catch_bp for p in points} == {bp.FULL}


def test_the_default_substitution_threshold_is_the_agreement_peak():
    """The result the reviewed labels unlocked, and the reason for `v1-reviewed`.

    Before the 30 benign-divergence labels carried a human's name, no setting of
    this dial could be scored for correctness — only for how much friction it
    bought. Now it can, and the shipped default is the unique maximum: agreement
    falls off on both sides of 80%, so the number is a choice the corpus
    supports rather than a guess nobody had examined.

    Asserted rather than quoted, because `thresholds.py` and `EVALUATION.md`
    both now rest on it being a peak and not a plateau.
    """
    from custodian.gate.thresholds import DEFAULT
    from eval.sweep import sweep

    points = {p.value_bp: p for p in
              sweep("substitution_faithful_bp", [5_000, 7_000, 8_000, 8_500, 9_000, 9_500])}
    assert DEFAULT.substitution_faithful_bp == 8_000
    assert all(p.benign_judged == 30 for p in points.values()), "labels must be human-reviewed"

    peak = points[8_000].benign_accuracy_bp
    assert peak == bp.FULL
    assert all(p.benign_accuracy_bp < peak for value, p in points.items() if value != 8_000)


def test_the_peak_survives_the_split_it_was_not_chosen_on():
    """Chosen on DEV, confirmed on TEST — the discipline the corpus exists for."""
    from eval.corpus.schema import Split
    from eval.sweep import sweep

    for split in (Split.DEV, Split.TEST):
        points = {p.value_bp: p for p in
                  sweep("substitution_faithful_bp", [7_000, 8_000, 9_000], split=split)}
        assert points[8_000].benign_accuracy_bp == bp.FULL
        assert points[7_000].benign_accuracy_bp < bp.FULL
        assert points[9_000].benign_accuracy_bp < bp.FULL
