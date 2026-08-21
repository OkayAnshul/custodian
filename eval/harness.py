"""Run the corpus through the gate and report what happened.

Two things this deliberately does *not* do.

It does not report one number. Approval rate on clean orders and catch rate on
adversarial ones move in opposite directions as a threshold shifts, and an
average across them hides the only interesting fact about the system.

It does not fold `PROPOSED` labels into headline figures. Those are the
benign-divergence cases, whose ground truth is a judgment nobody has signed off
yet. They are run and reported, under their own heading, marked.

    python -m eval.harness              # DEV split
    python -m eval.harness --split TEST # reported numbers
    python -m eval.harness --all
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml

from custodian import bp
from custodian.gate.decide import decide, escalations
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT, Thresholds
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent.parser import resolve
from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.catalog import CatalogSnapshot
from custodian.schemas.decision import Decision, Outcome
from custodian.schemas.decision_input import DecisionInput
from custodian.schemas.mandate import Mandate
from custodian.schemas.verdict import SemanticVerdict, VerdictLabel
from eval.corpus.schema import Case, CaseClass, Corpus, LabelSource, Split

CATALOG = Path(__file__).resolve().parents[1] / "data" / "catalog" / "kirana_export.csv"
CASES = Path(__file__).resolve().parent / "corpus" / "cases.yaml"
MERCHANT = "kirana-blr-001"
TAKEN_AT = "2026-08-28T09:00:00+00:00"
EVALUATED_AT = "2026-08-28T09:05:00+00:00"

MANDATE = Mandate(
    mandate_id="mnd-eval", max_amount_paise=5_000_000, per_transaction_cap_paise=400_000,
    valid_from="2026-08-01T00:00:00+00:00", valid_until="2026-09-30T00:00:00+00:00",
    merchant_allowlist=(MERCHANT,),
)


@dataclass(frozen=True, slots=True)
class Outcome_:
    """One graded case."""

    case: Case
    decision: Decision
    escalated: tuple[str, ...]

    @property
    def correct(self) -> bool:
        return self.decision.outcome is self.case.expect.outcome

    @property
    def reasons_hold(self) -> bool:
        """Did it decide for the stated reason, not merely reach the right verdict?"""
        raised = set(self.decision.reason_codes)
        return (
            set(self.case.expect.reason_codes) <= raised
            and not (set(self.case.expect.forbidden_reason_codes) & raised)
        )


@dataclass
class Metrics:
    """What a class of cases did."""

    name: str
    total: int = 0
    correct: int = 0
    reasons_correct: int = 0
    escalated_cases: int = 0
    escalated_lines: int = 0
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)

    def add(self, result: Outcome_) -> None:
        self.total += 1
        self.correct += result.correct
        self.reasons_correct += result.correct and result.reasons_hold
        if result.escalated:
            self.escalated_cases += 1
            self.escalated_lines += len(result.escalated)
        key = (str(result.case.expect.outcome), str(result.decision.outcome))
        self.confusion[key] = self.confusion.get(key, 0) + 1

    @property
    def accuracy_bp(self) -> int:
        return bp.from_ratio(self.correct, self.total) if self.total else 0

    def rate(self, expected: Outcome, actual: Outcome) -> int:
        matching = self.confusion.get((str(expected), str(actual)), 0)
        expected_total = sum(v for (e, _), v in self.confusion.items() if e == str(expected))
        return bp.from_ratio(matching, expected_total) if expected_total else 0


def load_corpus(path: Path = CASES) -> Corpus:
    return Corpus.model_validate(yaml.safe_load(path.read_text()))


def _snapshot_for(case: Case, base: CatalogSnapshot) -> CatalogSnapshot:
    """Apply a case's catalog tweaks, producing a distinct snapshot."""
    if not case.catalog_tweaks:
        return base
    tweaks = {t.item_id: t for t in case.catalog_tweaks}
    items = []
    for item in base.items:
        tweak = tweaks.get(item.item_id)
        if tweak is None:
            items.append(item)
            continue
        from custodian.ingest.sanitizer import sanitize

        update = {}
        if tweak.out_of_stock:
            update["in_stock"] = False
        if tweak.price_paise is not None:
            update["price_paise"] = tweak.price_paise
        if tweak.description is not None:
            cleaned = sanitize(tweak.description)
            update |= {"raw_description": tweak.description,
                       "description": cleaned.clean_text,
                       "sanitization": cleaned.finding}
        items.append(item.model_copy(update=update))
    return base.model_copy(update={"items": tuple(items)})


def build_input(case: Case, base: CatalogSnapshot, thresholds: Thresholds) -> DecisionInput:
    """Turn a case into exactly what the gate consumes."""
    snapshot = _snapshot_for(case, base)
    intent = resolve(
        {
            "goal": case.goal, "budget_paise": case.budget_paise,
            "merchant_scope": list(case.merchant_scope),
            "category_scope": list(case.category_scope) if case.category_scope else None,
            "substitution_policy": str(case.policy),
            "requested_items": [
                {"raw_text": r.raw_text, "quantity": r.quantity,
                 "max_unit_price_paise": r.max_unit_price_paise}
                for r in case.requested
            ],
        },
        intent_id="c",
    )
    lines = []
    for index, spec in enumerate(case.cart):
        item = snapshot.find(spec.item_id)
        lines.append(CartLine(
            line_id=f"c-l{index + 1}", item_id=spec.item_id,
            name_asserted=item.name if item else spec.item_id,
            quantity=spec.quantity,
            asserted_unit_price_paise=(
                spec.asserted_price_paise if spec.asserted_price_paise is not None
                else (item.price_paise if item else 0)
            ),
            satisfies_line_id=spec.satisfies,
        ))
    verdicts = tuple(
        SemanticVerdict(
            cart_line_id=line_id, requested_line_id="c-r1", label=VerdictLabel(label),
            score_bp=score, model="corpus-fixture", prompt_digest="0" * 64,
            raw_response=f'{{"label":"{label}","score_bp":{score}}}', obtained_at=EVALUATED_AT,
        )
        for line_id, label, score in case.verdicts
    )
    return DecisionInput(
        request_id=case.case_id, evaluated_at=EVALUATED_AT, intent=intent,
        cart=Cart(cart_id=f"{case.case_id}-cart", merchant_id=MERCHANT, lines=tuple(lines)),
        snapshot=snapshot, mandate=MANDATE, semantic_verdicts=verdicts, thresholds=thresholds,
    )


def run(corpus: Corpus, *, thresholds: Thresholds = DEFAULT, split: Split | None = None,
        tables: SubstitutionTables | None = None) -> list[Outcome_]:
    """Grade every case. No model is called — verdicts come from the corpus."""
    base, _ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    tables = tables or SubstitutionTables.from_taxonomy(default_taxonomy())
    cases = corpus.of_split(split) if split else corpus.cases

    results = []
    for case in cases:
        inp = build_input(case, base, thresholds)
        results.append(Outcome_(
            case=case, decision=decide(inp, tables=tables),
            escalated=escalations(inp, tables=tables),
        ))
    return results


def summarise(results: list[Outcome_]) -> dict[str, Metrics]:
    grouped: dict[str, Metrics] = {}
    for result in results:
        key = str(result.case.case_class)
        grouped.setdefault(key, Metrics(key)).add(result)
    overall = Metrics("ALL")
    for result in results:
        overall.add(result)
    grouped["ALL"] = overall
    return grouped


def report(results: list[Outcome_], *, thresholds: Thresholds, split: str) -> None:
    derived = [r for r in results
               if r.case.label_source in (LabelSource.DERIVED, LabelSource.HUMAN)]
    proposed = [r for r in results
                if r.case.label_source in (LabelSource.PROPOSED, LabelSource.MACHINE_REVIEWED)]
    metrics = summarise(derived)

    print(f"\nCorpus — {split} split, thresholds {thresholds.version}")
    print("─" * 78)
    print(f"  {'class':22} {'n':>4} {'correct':>9} {'reasons':>9}  escalations")
    for name in ("CLEAN", "ADVERSARIAL", "AMBIGUOUS", "ALL"):
        m = metrics.get(name)
        if not m:
            continue
        reasons = bp.from_ratio(m.reasons_correct, m.total) if m.total else 0
        print(f"  {name:22} {m.total:>4} {bp.to_str(m.accuracy_bp):>9} {bp.to_str(reasons):>9}"
              f"  {m.escalated_cases} cases / {m.escalated_lines} lines")

    clean = metrics.get("CLEAN")
    adversarial = metrics.get("ADVERSARIAL")
    print(f"\n  {'headline':22}")
    if clean:
        print(f"    clean approval rate    {bp.to_str(clean.rate(Outcome.APPROVE, Outcome.APPROVE)):>8}"
              f"   does it get out of the way?")
        print(f"    false-hold rate        {bp.to_str(clean.rate(Outcome.APPROVE, Outcome.HOLD)):>8}"
              f"   clean orders sent back to a human")
        print(f"    false-reject rate      {bp.to_str(clean.rate(Outcome.APPROVE, Outcome.REJECT)):>8}"
              f"   clean orders refused outright")
    if adversarial:
        caught = sum(v for (e, a), v in adversarial.confusion.items() if a != str(Outcome.APPROVE))
        print(f"    adversarial catch rate {bp.to_str(bp.from_ratio(caught, adversarial.total)):>8}"
              f"   does it work?")
        print(f"    false-approval rate    "
              f"{bp.to_str(bp.from_ratio(adversarial.total - caught, adversarial.total)):>8}"
              f"   attacks that got through")

    if clean and adversarial and clean.accuracy_bp == bp.FULL and adversarial.accuracy_bp == bp.FULL:
        print(f"\n  what a perfect derived score does and does not mean")
        print(f"    CLEAN, ADVERSARIAL and AMBIGUOUS have labels that follow from how each case")
        print(f"    was built. A forged price is a rejection by construction. Scoring 100% on")
        print(f"    them says the implementation matches its specification — it does not say the")
        print(f"    specification is right. The class where that question actually lives is")
        print(f"    benign divergence, and its labels are still drafts.")

    if proposed:
        matched = sum(r.correct for r in proposed)
        machine = [r for r in proposed if r.case.label_source is LabelSource.MACHINE_REVIEWED]
        stage = "MACHINE-REVIEWED" if machine else "DRAFTED"
        print(f"\n  benign divergence — {len(proposed)} cases, labels {stage}, "
              f"AWAITING HUMAN REVIEW")
        print(f"    agreement with these labels {bp.to_str(bp.from_ratio(matched, len(proposed))):>8}")
        if machine:
            reviewers = sorted({r.case.reviewed_by for r in machine if r.case.reviewed_by})
            print(f"    reviewed by: {', '.join(reviewers)}")
            print(f"    A model's second pass, not a human sign-off. It is a stronger label than")
            print(f"    a first draft and it is still the same kind of judgment being scored")
            print(f"    against itself, so this is not a headline number either.")
        else:
            print(f"    Not a headline number. These labels were drafted, not judged, and a model")
            print(f"    scored against labels it drafted is measuring its own consistency.")
        if machine and bp.from_ratio(matched, len(proposed)) >= 9_500:
            print(f"\n    ⚠ Near-total agreement between a model's labels and a model-built")
            print(f"      gate is evidence of circularity, not of correctness. A first draft")
            print(f"      of these labels agreed 86.67%; a second pass by the same model")
            print(f"      raised it by moving labels toward the system's behaviour. The")
            print(f"      lower number was the more informative one. Treat this as a")
            print(f"      measurement that has not been taken.")
        if disagreements := [r for r in proposed if not r.correct]:
            print(f"\n    {len(disagreements)} case(s) where the gate and the label disagree —")
            print(f"    the most useful place for a human to start:")
            for r in disagreements[:8]:
                print(f"      {r.case.case_id:18} label {r.case.expect.outcome:8} "
                      f"gate {r.decision.outcome:8} {r.case.rationale[:52]}")

    failures = [r for r in derived if not r.correct]
    if failures:
        print(f"\n  {len(failures)} derived case(s) decided wrongly:")
        for result in failures[:12]:
            print(f"    {result.case.case_id:24} expected {result.case.expect.outcome:8} "
                  f"got {result.decision.outcome:8} align {bp.to_str(result.decision.alignment_bp)}")
    wrong_reasons = [r for r in derived if r.correct and not r.reasons_hold]
    if wrong_reasons:
        print(f"\n  {len(wrong_reasons)} case(s) right for the wrong reason:")
        for result in wrong_reasons[:8]:
            missing = set(result.case.expect.reason_codes) - set(result.decision.reason_codes)
            print(f"    {result.case.case_id:24} missing {sorted(str(m) for m in missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["DEV", "TEST"], default="DEV")
    parser.add_argument("--all", action="store_true", help="every case, both splits")
    args = parser.parse_args()

    corpus = load_corpus()
    split = None if args.all else Split(args.split)
    results = run(corpus, split=split)
    report(results, thresholds=DEFAULT, split="ALL" if args.all else args.split)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
