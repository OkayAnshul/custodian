"""Record real model responses, so the replay fixtures are actually recordings.

Every "recorded" response in this project was written by hand. `RecordedScorer`
and `RecordedParser` replay answers nobody ever received, which makes their
names an overstatement — a mild version of the label-fabrication problem in
BROKE.md 010, and one worth fixing for the same reason.

This makes the calls for real and writes what came back, with provenance:
which model, which provider, which prompt digest, and when. After it runs, the
class names are true and the corpus escalations are genuine model behaviour
rather than a guess at model behaviour.

    export GROQ_API_KEY=...
    python scripts/record_fixtures.py --provider groq

Incremental and resumable: existing recordings are kept, and a run that dies to
a rate limit does not lose the ones already made. Re-recording a digest requires
--overwrite, so a rerun cannot silently replace a good response with a worse one.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from custodian.clock import utc_now
from custodian.gate.binding import bind
from custodian.gate.decide import escalations
from custodian.gate.semantic import ScoringError, build_question, prompt_digest
from custodian.gate.substitution import SubstitutionTables
from custodian.gate.thresholds import DEFAULT
from custodian.ingest.snapshot import ingest_csv
from custodian.ingest.taxonomy import default_taxonomy
from custodian.intent import prompt as intent_prompt
from custodian.intent.parser import ParseError
from eval.harness import CATALOG, MERCHANT, TAKEN_AT, build_input, load_corpus

FIXTURES = ROOT / "data" / "fixtures" / "model_responses.json"


@dataclass
class Recording:
    """One real response, with enough provenance to tell it from an invention."""

    kind: str            # "verdict" | "intent"
    prompt_digest: str
    provider: str
    model: str
    obtained_at: str
    #: The question as sent, kept so a reader can check what was actually asked.
    question: str
    raw_response: str
    #: Which corpus case or demo beat this came from, for traceability.
    source: str


def _load() -> dict[str, Recording]:
    if not FIXTURES.exists():
        return {}
    body = json.loads(FIXTURES.read_text())
    return {e["prompt_digest"]: Recording(**e) for e in body.get("entries", [])}


def _save(records: dict[str, Recording], provider: str) -> None:
    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    FIXTURES.write_text(json.dumps({
        "version": "fixtures-v1",
        "note": "Real model responses. Written by scripts/record_fixtures.py, not by hand.",
        "last_provider": provider,
        "last_run": utc_now(),
        "entries": [asdict(r) for r in sorted(records.values(), key=lambda r: r.prompt_digest)],
    }, indent=2, ensure_ascii=False) + "\n")


def _scorer(provider: str):
    if provider == "groq":
        from custodian.gate.groq_scorer import GroqScorer
        return GroqScorer()
    from custodian.gate.semantic import ClaudeScorer
    return ClaudeScorer()


def _parser(provider: str):
    if provider == "groq":
        from custodian.intent.groq_parser import GroqParser
        return GroqParser()
    from custodian.intent.claude import ClaudeParser
    return ClaudeParser()


def escalating_pairs():
    """Every substitution in the corpus that the deterministic layer cannot settle."""
    corpus = load_corpus()
    base, _ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    tables = SubstitutionTables.from_taxonomy(default_taxonomy())

    for case in corpus.cases:
        inp = build_input(case, base, DEFAULT)
        needed = escalations(inp, tables=tables)
        if not needed:
            continue
        report = bind(inp.intent, inp.cart, inp.snapshot, tables=tables, thresholds=DEFAULT)
        for bound in report.lines:
            if bound.line.line_id not in needed or bound.requested is None:
                continue
            item = inp.snapshot.find(bound.line.item_id)
            if item is not None:
                yield case.case_id, inp.intent.goal, bound.requested, item


#: The goals the demo and the settlement script parse. Recorded so the demo can
#: show a real parse without a live call during a take.
DEMO_GOALS = [
    ("demo", "two tins of coconut milk, thai red curry paste and lemongrass for a "
             "curry tonight, under Rs 3000"),
    ("demo-spice", "buy whole turmeric for a pickle"),
    # Kept deliberately: the model refuses to expand this into ingredients,
    # correctly, because the prompt forbids inventing items the human did not
    # name. The result is one unplaceable line, which holds. That is an honest
    # limit of the system and worth having a recording of.
    ("underspecified", "ingredients for a thai curry, under Rs 2000"),
]


#: Substitution questions the demo asks that no corpus case covers. The digest
#: depends on the goal as well as the pair, so a differently-worded goal is a
#: different question and needs its own recording.
DEMO_SUBSTITUTIONS = [
    ("demo-spice", "buy whole turmeric for a pickle", "whole turmeric", "SKU032"),
]


def demo_substitution_pairs():
    from custodian.intent.parser import resolve

    base, _ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    for source, goal, asked, sku in DEMO_SUBSTITUTIONS:
        intent = resolve({"goal": goal, "substitution_policy": "SAME_BASE",
                          "requested_items": [{"raw_text": asked, "quantity": 1}]},
                         intent_id="demo")
        yield source, goal, intent.requested_items[0], base.find(sku)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq")
    parser.add_argument("--overwrite", action="store_true",
                        help="re-record digests that already have a response")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be recorded, make no calls")
    args = parser.parse_args()

    records = _load()
    pairs = list(escalating_pairs()) + list(demo_substitution_pairs())
    seen: set[str] = set()
    todo_verdicts = []
    for case_id, goal, requested, offered in pairs:
        digest = prompt_digest(goal, requested, offered)
        if digest in seen:
            continue  # the same question twice is one recording
        seen.add(digest)
        if digest in records and not args.overwrite:
            continue
        todo_verdicts.append((case_id, goal, requested, offered, digest))

    todo_intents = [
        (source, goal, intent_prompt.prompt_digest(goal))
        for source, goal in DEMO_GOALS
        if intent_prompt.prompt_digest(goal) not in records or args.overwrite
    ]
    # The same goal appears twice in DEMO_GOALS; one recording covers both.
    todo_intents = list({d: (s, g, d) for s, g, d in todo_intents}.values())

    print(f"escalating substitutions in the corpus : {len(pairs)}")
    print(f"distinct questions among them          : {len(seen)}")
    print(f"verdicts to record                     : {len(todo_verdicts)}")
    print(f"intents to record                      : {len(todo_intents)}")
    print(f"already recorded                       : {len(records)}")

    if args.dry_run:
        for case_id, goal, requested, offered, _ in todo_verdicts[:8]:
            print(f"  {case_id:18} {requested.raw_text:22} -> {offered.name[:34]}")
        return 0
    if not todo_verdicts and not todo_intents:
        print("\nnothing to do. --overwrite to re-record.")
        return 0

    scorer, intent_parser = _scorer(args.provider), _parser(args.provider)
    print(f"\nrecording against {scorer.model} ({args.provider})\n")

    failures = 0
    for index, (case_id, goal, requested, offered, digest) in enumerate(todo_verdicts, 1):
        try:
            verdict = scorer.score(goal=goal, requested=requested, offered=offered,
                                   cart_line_id="rec")
        except ScoringError as exc:
            # Save what we have. A rate limit mid-run must not cost the rest.
            failures += 1
            print(f"  [{index}/{len(todo_verdicts)}] {case_id:18} FAILED — {str(exc)[:56]}")
            _save(records, args.provider)
            continue
        records[digest] = Recording(
            kind="verdict", prompt_digest=digest, provider=args.provider,
            model=verdict.model, obtained_at=verdict.obtained_at,
            question=build_question(goal, requested, offered),
            raw_response=verdict.raw_response, source=case_id,
        )
        print(f"  [{index}/{len(todo_verdicts)}] {case_id:18} "
              f"{requested.raw_text[:20]:22} -> {str(verdict.label):11} {verdict.score_bp:>5}bp")
        _save(records, args.provider)

    for source, goal, digest in todo_intents:
        try:
            result = intent_parser.parse(goal, intent_id="rec")
        except ParseError as exc:
            failures += 1
            print(f"  intent {source:14} FAILED — {str(exc)[:56]}")
            continue
        records[digest] = Recording(
            kind="intent", prompt_digest=digest, provider=args.provider,
            model=result.model, obtained_at=result.obtained_at, question=goal,
            raw_response=result.raw_response, source=source,
        )
        print(f"  intent {source:14} {len(result.intent.requested_items)} items parsed")
        _save(records, args.provider)

    _save(records, args.provider)
    print(f"\nwrote {FIXTURES.relative_to(ROOT)} — {len(records)} recordings"
          + (f", {failures} failed" if failures else ""))
    print("\nThese are real responses. RecordedScorer and RecordedParser now replay")
    print("answers that were actually received, which is what their names claim.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
