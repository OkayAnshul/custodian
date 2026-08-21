"""Review the drafted benign-divergence labels.

These are the 30 cases whose ground truth is a judgment about cooking rather
than a consequence of how the case was built. A model cannot supply them
honestly — scored against labels it drafted, it would be measuring its own
consistency — so this exists to make a human's pass over them fast rather than
to do it for them.

Three modes, so the work can happen wherever it is convenient:

    python -m eval.corpus.review --sheet                      # write REVIEW.md
    python -m eval.corpus.review --as you@example.com         # interactive
    python -m eval.corpus.review --apply --as you@example.com # read decisions.txt

``--as`` is required for anything that writes a label. A reviewed label carries
the name of whoever made the call, because an unattributed judgment cannot be
told apart from a relabelled draft.

Each case is presented with everything needed to judge it and nothing that would
lead the judgment: the request, the offered item, both attribute placements, the
table scores that produced the current behaviour, and what the gate decides
today. The drafted call and its reasoning are shown last, marked as a draft.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import yaml

from custodian import bp
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.money import format_inr
from custodian.schemas.decision import Outcome
from eval.corpus.schema import Case, CaseClass, Corpus, LabelSource
from eval.harness import CATALOG, MERCHANT, TAKEN_AT, build_input
from custodian.gate.decide import decide, escalations

CASES = Path(__file__).resolve().parent / "cases.yaml"
SHEET = Path(__file__).resolve().parent / "REVIEW.md"
DECISIONS = Path(__file__).resolve().parent / "decisions.txt"

VALID = {"APPROVE", "HOLD", "REJECT"}


def _evidence(case: Case, snapshot, tables) -> dict[str, str]:
    """Everything needed to judge this case, gathered once."""
    requested = case.requested[0]
    item = snapshot.find(case.cart[0].item_id)
    inp = build_input(case, snapshot, DEFAULT)
    placed = inp.intent.requested_items[0]
    decision = decide(inp, tables=tables)

    base_score = tables.base(placed.base, item.base)
    form_score = tables.form(placed.form, item.form)
    return {
        "asked": requested.raw_text,
        "offered": item.name,
        "asked_placed": f"{placed.base}/{placed.form}",
        "offered_placed": f"{item.base}/{item.form}",
        "base_score": "no recorded relationship" if base_score is None else str(base_score),
        "form_score": "unlisted — escalates" if form_score is None else str(form_score),
        "policy": str(case.policy),
        "price": format_inr(item.price_paise),
        "gate_says": str(decision.outcome),
        "alignment": bp.to_str(decision.alignment_bp),
        "confidence": bp.to_str(decision.confidence_bp),
        "escalates": "yes" if escalations(inp, tables=tables) else "no",
    }


def _load() -> tuple[Corpus, list[Case]]:
    corpus = Corpus.model_validate(yaml.safe_load(CASES.read_text()))
    return corpus, list(corpus.awaiting_review())


def _context():
    snapshot, _ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    return snapshot, SubstitutionTables.from_taxonomy(default_taxonomy())


def write_sheet() -> int:
    corpus, pending = _load()
    snapshot, tables = _context()
    if not pending:
        print("Nothing awaiting review.")
        return 0

    lines = [
        "# Benign divergence — labels awaiting review",
        "",
        f"{len(pending)} cases. These are the ones whose ground truth is a judgment about "
        "cooking rather than a consequence of how the case was built, and they are the class "
        "the project's difficulty actually lives in.",
        "",
        "**The question for each:** if someone asked for the first thing and received the "
        "second, would their intent be satisfied?",
        "",
        "- `APPROVE` — a cook would accept this without being asked.",
        "- `HOLD` — it depends on the dish, or the buyer should be asked first.",
        "- `REJECT` — this does not serve the same purpose.",
        "",
        "Record your calls in `eval/corpus/decisions.txt`, one per line, then run "
        "`python -m eval.corpus.review --apply`:",
        "",
        "```",
        "benign-001: APPROVE",
        "benign-002: HOLD        # optional note after a #",
        "```",
        "",
        "Anything you do not list keeps its drafted label and stays marked as a draft.",
        "",
        "---",
        "",
    ]

    for case in pending:
        e = _evidence(case, snapshot, tables)
        lines += [
            f"## `{case.case_id}` — {e['asked']} → {e['offered']}",
            "",
            f"| | |",
            f"|---|---|",
            f"| asked for | **{e['asked']}** — placed as `{e['asked_placed']}` |",
            f"| offered | **{e['offered']}** ({e['price']}) — placed as `{e['offered_placed']}` |",
            f"| substitution policy | `{e['policy']}` |",
            f"| base score | {e['base_score']} |",
            f"| form score | {e['form_score']} |",
            f"| gate decides today | **{e['gate_says']}** (alignment {e['alignment']}, "
            f"confidence {e['confidence']}, escalates: {e['escalates']}) |",
            "",
            f"<details><summary>Drafted call — <b>{case.expect.outcome}</b> — click to see the "
            f"reasoning</summary>",
            "",
            f"> {case.rationale}",
            "",
            "</details>",
            "",
            "---",
            "",
        ]

    SHEET.write_text("\n".join(lines))
    print(f"wrote {SHEET.relative_to(Path.cwd())} — {len(pending)} cases")
    print(f"record your calls in {DECISIONS.relative_to(Path.cwd())}, then --apply")
    return 0


def interactive(actor: str) -> int:
    corpus, pending = _load()
    snapshot, tables = _context()
    if not pending:
        print("Nothing awaiting review.")
        return 0

    print(f"\n{len(pending)} cases awaiting review. "
          f"[a]pprove  [h]old  [r]eject  [enter] keep draft  [q]uit\n")
    calls: dict[str, str] = {}
    for index, case in enumerate(pending, 1):
        e = _evidence(case, snapshot, tables)
        print(f"─── {index}/{len(pending)}  {case.case_id} " + "─" * 40)
        print(f"  asked for   {e['asked']}   ({e['asked_placed']})")
        print(f"  offered     {e['offered']}   ({e['offered_placed']}, {e['price']})")
        print(f"  policy      {e['policy']}")
        print(f"  scores      base {e['base_score']}   form {e['form_score']}")
        print(f"  gate today  {e['gate_says']}  (escalates: {e['escalates']})")
        print(f"  drafted     {case.expect.outcome} — {case.rationale[:150]}")
        try:
            answer = input("  your call > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nstopping — nothing written")
            return 1
        if answer == "q":
            break
        chosen = {"a": "APPROVE", "h": "HOLD", "r": "REJECT"}.get(answer)
        if chosen:
            calls[case.case_id] = chosen
        print()

    if not calls:
        print("no calls recorded")
        return 0
    return _apply(calls, actor)


def apply_file(actor: str) -> int:
    if not DECISIONS.exists():
        print(f"no {DECISIONS.relative_to(Path.cwd())} — run --sheet first")
        return 1
    calls: dict[str, str] = {}
    for number, raw in enumerate(DECISIONS.read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            print(f"line {number}: expected 'case_id: OUTCOME', got {raw.strip()!r}")
            return 1
        case_id, _, outcome = line.partition(":")
        outcome = outcome.strip().upper()
        if outcome not in VALID:
            print(f"line {number}: {outcome!r} is not one of {sorted(VALID)}")
            return 1
        calls[case_id.strip()] = outcome
    return _apply(calls, actor)


def _apply(calls: dict[str, str], actor: str) -> int:
    corpus, _ = _load()
    known = {c.case_id for c in corpus.cases}
    if unknown := sorted(set(calls) - known):
        print(f"no such case: {unknown}")
        return 1

    updated, changed = [], 0
    for case in corpus.cases:
        if case.case_id not in calls:
            updated.append(case)
            continue
        outcome = Outcome(calls[case.case_id])
        if outcome is not case.expect.outcome:
            changed += 1
        updated.append(case.model_copy(update={
            "label_source": LabelSource.HUMAN,
            "reviewed_by": actor,
            "expect": case.expect.model_copy(update={"outcome": outcome}),
        }))

    reviewed = Corpus(version=corpus.version, cases=tuple(updated))
    CASES.write_text(yaml.safe_dump(reviewed.model_dump(mode="json"), sort_keys=False,
                                    width=100, allow_unicode=True))
    remaining = len(reviewed.awaiting_review())
    print(f"applied {len(calls)} label(s) as {actor} — {changed} differ from the draft")
    print(f"{remaining} still awaiting review")
    if remaining == 0:
        print("\nEvery label is now human-authored. The benign-divergence numbers are quotable.")
    print("\nre-run:  python -m eval.harness --all")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", action="store_true", help="write REVIEW.md")
    parser.add_argument("--apply", action="store_true", help="read decisions.txt")
    parser.add_argument("--as", dest="actor", metavar="NAME",
                        help="who is making these calls; required to write a label")
    args = parser.parse_args()
    if args.sheet:
        return write_sheet()
    if not args.actor:
        parser.error("--as NAME is required to record a label. A reviewed label must name "
                     "who made the call.")
    if args.apply:
        return apply_file(args.actor)
    return interactive(args.actor)


if __name__ == "__main__":
    raise SystemExit(main())
