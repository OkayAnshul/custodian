"""The threshold sweep: the curve, not a point.

A single accuracy figure at one threshold is an assertion. What a merchant
actually needs to know is the shape of the trade: how much friction buys how
much safety, and where the curve bends.

Two dials are swept independently because they do different work.

``min_confidence_bp`` governs abstention. Raising it holds more orders the gate
was unsure about — which costs friction and buys nothing against attacks that
deterministic checks already reject. That asymmetry is the point: most of what
this system catches, it catches for free.

**What is measured, and why it does not need ground truth.** Accuracy against
labels is reported only for the derived classes. Friction is reported as a *hold
rate* on the benign-divergence set — what fraction of plausible substitutions get
sent back to a human — and that needs no labels at all, because it is a fact
about the system's behaviour rather than a claim about whether it was right.
That distinction matters: those labels are drafts, and tuning a threshold to
agree with a draft is how a number gets chosen for the wrong reason and then
reported as though it had been measured.

``approve_min_alignment_bp`` governs how close to perfect a clean order must
look. It bites only on orders where every dimension passed, since a failed
dimension already caps the outcome at hold (ADR-020).

    python -m eval.sweep
    python -m eval.sweep --split TEST --csv docs/sweep.csv
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custodian import bp
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT, Thresholds
from custodian.ingest.taxonomy import default_taxonomy
from custodian.schemas.decision import Outcome
from eval.corpus.schema import CaseClass, LabelSource, Split
from eval.harness import load_corpus, run


@dataclass(frozen=True, slots=True)
class Point:
    """One threshold setting and what it cost."""

    dial: str
    value_bp: int
    clean_approval_bp: int
    false_hold_bp: int
    adversarial_catch_bp: int
    false_approval_bp: int
    ambiguous_hold_bp: int
    #: Fraction of benign-divergence orders sent back to a human. Needs no
    #: ground truth — it is behaviour, not correctness.
    benign_hold_bp: int
    escalation_rate_bp: int

    @property
    def friction(self) -> str:
        """False holds per hundred clean orders — the number a merchant feels."""
        return f"{self.false_hold_bp / 100:.0f} in 100"


def _rate(results, case_class: CaseClass, expected: Outcome, actual: Outcome) -> int:
    subset = [r for r in results if r.case.case_class is case_class
              and r.case.expect.outcome is expected]
    if not subset:
        return 0
    return bp.from_ratio(sum(r.decision.outcome is actual for r in subset), len(subset))


def _caught(results) -> int:
    subset = [r for r in results if r.case.case_class is CaseClass.ADVERSARIAL]
    if not subset:
        return 0
    return bp.from_ratio(sum(r.decision.outcome is not Outcome.APPROVE for r in subset), len(subset))


def sweep(dial: str, values: list[int], *, split: Split | None = None) -> list[Point]:
    """Vary one dial, holding everything else at the default."""
    corpus = load_corpus()
    tables = SubstitutionTables.from_taxonomy(default_taxonomy())
    short = {"min_confidence_bp": "conf", "approve_min_alignment_bp": "align",
             "reject_max_alignment_bp": "rej", "substitution_faithful_bp": "subf"}

    points: list[Point] = []
    for value in values:
        try:
            # Version strings are capped at 32 characters. Building one from the
            # full dial name silently overflowed and every point in the sweep was
            # discarded as an invalid setting — a flat curve that looked like a
            # finding. See BROKE.md 008.
            thresholds = Thresholds.model_validate(
                DEFAULT.model_dump() | {dial: value, "version": f"sw-{short.get(dial, dial)}-{value}"}
            )
        except Exception:
            continue  # a setting the invariants forbid is not a data point
        results = run(corpus, thresholds=thresholds, split=split, tables=tables)
        graded = [r for r in results if r.case.label_source is not LabelSource.PROPOSED]
        benign = [r for r in results if r.case.case_class is CaseClass.BENIGN_DIVERGENCE]
        held = sum(r.decision.outcome is Outcome.HOLD for r in benign)
        escalating = sum(1 for r in results if r.escalated)
        points.append(Point(
            dial=dial, value_bp=value,
            clean_approval_bp=_rate(graded, CaseClass.CLEAN, Outcome.APPROVE, Outcome.APPROVE),
            false_hold_bp=_rate(graded, CaseClass.CLEAN, Outcome.APPROVE, Outcome.HOLD),
            adversarial_catch_bp=_caught(graded),
            false_approval_bp=bp.FULL - _caught(graded),
            ambiguous_hold_bp=_rate(graded, CaseClass.AMBIGUOUS, Outcome.HOLD, Outcome.HOLD),
            benign_hold_bp=bp.from_ratio(held, len(benign)) if benign else 0,
            escalation_rate_bp=bp.from_ratio(escalating, len(results)) if results else 0,
        ))
    return points


def render(points: list[Point], title: str) -> None:
    print(f"\n{title}")
    print("─" * 78)
    if not points:
        print("  no valid settings in this range")
        return
    print(f"  {'threshold':>10}  {'clean approve':>14} {'adv. catch':>11} "
          f"{'substitutions held':>19} {'escalation rate':>16}")
    for point in points:
        marker = "  <- default" if point.value_bp == getattr(DEFAULT, point.dial) else ""
        print(f"  {bp.to_str(point.value_bp):>10}  {bp.to_str(point.clean_approval_bp):>14} "
              f"{bp.to_str(point.adversarial_catch_bp):>11} {bp.to_str(point.benign_hold_bp):>19} "
              f"{bp.to_str(point.escalation_rate_bp):>16}{marker}")

    lo, hi = points[0].benign_hold_bp, points[-1].benign_hold_bp
    if lo != hi:
        print(f"\n  friction range: {bp.to_str(min(lo, hi))} to {bp.to_str(max(lo, hi))} of "
              f"plausible substitutions sent back to a human.")
    bends = [p for p in points if p.false_hold_bp > 0]
    if bends:
        first = min(bends, key=lambda p: p.value_bp)
        print(f"  clean orders start being held at {bp.to_str(first.value_bp)}: {first.friction}.")
    if all(p.adversarial_catch_bp == bp.FULL for p in points):
        print(f"  catch rate is flat at 100% across the whole range — every adversarial case")
        print(f"  in this corpus is settled by a deterministic check, so no threshold buys")
        print(f"  safety here. The dial only spends friction. That is worth knowing before")
        print(f"  anyone tunes it upward hoping for protection it cannot provide.")


def to_csv(points: list[Point], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dial", "threshold_bp", "clean_approval_bp", "false_hold_bp",
                         "adversarial_catch_bp", "false_approval_bp", "ambiguous_hold_bp"])
        for p in points:
            writer.writerow([p.dial, p.value_bp, p.clean_approval_bp, p.false_hold_bp,
                             p.adversarial_catch_bp, p.false_approval_bp, p.ambiguous_hold_bp])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["DEV", "TEST", "ALL"], default="DEV")
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    split = None if args.split == "ALL" else Split(args.split)

    confidence = sweep("min_confidence_bp", list(range(0, 10_001, 1_000)), split=split)
    substitution = sweep("substitution_faithful_bp",
                         [5_000, 6_000, 7_000, 8_000, 8_500, 9_000, 9_500], split=split)
    render(confidence, f"Abstention dial — min_confidence_bp ({args.split} split)")

    alignment = sweep("approve_min_alignment_bp",
                      [5_000, 6_000, 7_000, 8_000, 9_000, 9_500, 9_900, 10_000], split=split)
    render(alignment, f"Strictness dial — approve_min_alignment_bp ({args.split} split)")

    render(substitution, f"Escalation band — substitution_faithful_bp ({args.split} split)")

    if args.csv:
        to_csv(confidence + alignment + substitution, args.csv)
        print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
