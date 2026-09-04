# Evaluation

## What is measured, and what it rests on

Three of the four case classes have labels that follow from how each case was constructed. A cart quoting a price the catalog does not have is a rejection by definition; a cart of in-stock items at catalog prices answering every request exactly is an approval by definition. Those are marked `DERIVED`.

**The benign-divergence class does not work that way.** Whether coconut cream stands in acceptably for coconut milk is a judgment about cooking. For most of this project's life its 30 labels were marked `PROPOSED` — drafted, not judged — reported under their own heading and folded into no headline figure, because *a model scored against labels it drafted is measuring its own consistency*.

**They have now been reviewed by a person.** All 30 carry `label_source: HUMAN` and the reviewer's name; `eval/corpus/REVIEW.md` records what was decided against what evidence, and `eval/corpus/decisions.txt` records why. That is what makes the numbers below quotable — and it is also a narrow piece of evidence, so §"What the agreement is worth" states its three bounds rather than leaving a reader to find them.

This is enforced, not remembered: `Case` refuses to construct a `BENIGN_DIVERGENCE` case with a `DERIVED` label, and the schema refuses a reviewed label with nobody's name on it.

## Shape

| Class | n | What it tests |
|---|---:|---|
| Clean | 60 | Does it get out of the way? |
| Benign divergence | 30 | Can it tell a reasonable substitution from a bad one? |
| Adversarial | 15 | Does it work? |
| Ambiguous | 15 | Does it know when it does not know? |

Split DEV 82 / TEST 38, stratified so every class appears in both. Thresholds are chosen on DEV; headline numbers are reported on TEST. Tuning and reporting on one set is the mistake "one cherry-picked match proves nothing" warns about.

Every case carries a written rationale. A case without a stated reason is a number nobody can check.

## Results

TEST split, `thresholds v1-reviewed`:

```
class                 n   correct   reasons  escalations
CLEAN                19   100.00%   100.00%  0 cases / 0 lines
BENIGN_DIVERGENCE    10   100.00%   100.00%  5 cases / 5 lines
ADVERSARIAL           5   100.00%   100.00%  0 cases / 0 lines
AMBIGUOUS             4   100.00%   100.00%  1 cases / 1 lines
ALL                  38   100.00%   100.00%  6 cases / 6 lines

clean approval rate     100.00%
false-hold rate           0.00%
false-reject rate         0.00%
adversarial catch rate  100.00%
false-approval rate       0.00%
```

`reasons` is stricter than `correct`: it requires the decision to raise the reason codes the case expects and none of the codes it forbids. A right verdict for the wrong reason is a case that will drift without warning.

**What 100% on the derived classes does not mean.** It says the implementation matches its specification. It does not say the specification is right. That question lives in benign divergence — which is now answerable, and is answered below.

## The result the review unlocked

While the benign labels were drafts, no setting of the substitution dial could be scored for *correctness*, only for how much friction it bought. With the labels reviewed, each setting can be scored against a person's judgment — and the shipped default turns out to be the unique maximum:

```
substitution_faithful_bp   agreement   substitutions held   clean approval
        50%                  73.33%          46.67%             100%
        60%                  73.33%          46.67%             100%
        70%                  80.00%          53.33%             100%
        80%  (default)      100.00%          73.33%             100%
        85%                  93.33%          80.00%             100%
        90%                  80.00%          93.33%             100%
        95%                  80.00%          93.33%              98.33%
```

Agreement falls off on **both** sides of 80%, so this is a peak rather than a plateau — and it holds separately on DEV (n=20) and on TEST (n=10), which is the split discipline doing the job it exists for. Two tests assert both facts, because `thresholds.py` and this file now rest on them.

**Not one threshold value moved.** The version string changed from `v0-untuned` to `v1-reviewed` for that reason: the numbers were checked and left alone, not fitted. Calling them "tuned" would claim more than happened.

The other two dials are flat on agreement: `min_confidence_bp` changes nothing across its whole range, and `approve_min_alignment_bp` holds 100% from 50% to 95% before falling to 80%. The default sits inside that plateau.

## What the agreement is worth

100% agreement between a gate and its reviewer is exactly the shape of number that deserves suspicion, so here is what bounds it. The harness prints all three itself, every run:

- **One reviewer, no adjudication.** 15 distinct substitutions, each judged once and applied to both variants of its pair.
- **The reviewer saw the gate's current call while judging.** `REVIEW.md` shows a "gate decides today" column deliberately — it is context a reviewer needs — and it makes anchoring possible and agreement cheaper than an independent blind pass would be.
- **It is one catalog.** The claim is that the gate matches this reviewer on these 15 substitutions, not that it matches cooks in general.

What it *is*: a measurement where there was none. The threshold peak above is not derivable from drafted labels at all, and everything the harness reported about this class before was explicitly not a result.

## The governing rule the review settled

The reviewer's first decision was not about food. It was about what the three outcomes mean:

> **REJECT means a hard constraint failed, or the two items have no relationship. Anything related but possibly wrong is HOLD** — a shopkeeper out of atta offers maida and lets the customer decide; they do not refuse the sale.

That decides several cases at once and has a consequence worth stating plainly: **the only REJECT in this class is `benign-009`**, where the base changed under a `SAME_BASE` policy. Every judgment about cooking lands on APPROVE or HOLD, and no substitution is ever rejected on its merits — only on a constraint. That is the open question in **ADR-028**, and the review closes it in favour of the current design.

The four cases previously flagged as most contestable were all reviewed under that rule:

| Case | Substitution | Reviewed call | Note |
|---|---|---|---|
| `benign-011` | atta → maida | HOLD | The draft said REJECT; a second pass moved it, and this is now a considered call rather than an inherited one |
| `benign-015` | chana dal → moong dal | HOLD | Same history, same rule applied |
| `benign-007` | mustard seeds → mustard oil | HOLD | You cannot temper with oil — but the two are genuinely related, so it asks |
| `benign-008` | sunflower → groundnut oil | APPROVE | Under `EQUIVALENT`, where the human invited substitutes and the equivalence is listed. Groundnut is peanut, and an allergen check is a control this system does not have — noted in `LIMITATIONS.md` rather than smuggled into this label |

## Cost

24 of 162 cart lines (14.8%) escalate to a model, concentrated in benign divergence. **Zero adversarial cases reach a model** — `escalations()` returns nothing when a hard constraint has already failed, so a rejected cart costs no tokens. That is the "the semantic scorer never sees a case the arithmetic settled" guarantee implemented rather than asserted, and it is tested by handing the service a scorer that raises if touched.

## The threshold sweep

**The adversarial catch rate does not move across any dial.** Every attack in this corpus is settled by a deterministic check, so tightening a threshold spends friction and buys no safety. Worth knowing before anyone tunes it upward hoping for protection it cannot provide.

Friction is measured as a *hold rate*, which needs no ground truth: what fraction of plausible substitutions get sent back to a human is a fact about behaviour, not a claim about correctness. That is what let the benign-divergence cases contribute to the cost curve while their labels were still drafts — and it is reported alongside agreement now rather than replaced by it, because "held more often" and "agreed with more often" are different claims and a dial can buy one while spending the other.

## Two labels a real model disagrees with

Recording the fixtures against a live model (`openai/gpt-oss-120b`) produced two disagreements with the labels, and they survived the human review:

| Case | Substitution | Reviewed | Model | Why it is interesting |
|---|---|---|---|---|
| `benign-oos-003` | coconut milk → coconut powder | HOLD | `FAITHFUL` 8500 | The goal says *"or the closest thing you can get"* |
| `benign-oos-005` | coriander powder → whole seeds | HOLD | `FAITHFUL` 8700 | Same phrasing |

The in-stock variants of both, whose goals say only *"for tonight's cooking"*, came back `UNFAITHFUL` at 800–1000. **Same substitution, opposite verdict, and the only difference is that the human signalled flexibility.**

**This is the one thing the review left open**, and it is a design question rather than a labelling one. The reviewer's calls mirror across each pair, on the stated ground that the two variants differ only in prose the gate never sees. The gate's channel for "I am flexible" is the `substitution_policy` field, not the goal text — and both these cases are `SAME_BASE`, so a buyer who meant it should have sent `EQUIVALENT`. Whether the parser should *infer* the policy from phrasing like "or the closest thing you can get" is unresolved, and it would move model position #1 from reading a request to setting the authority a later check runs under. That is a bigger change than it looks and it is not made here.

One general observation, since it shapes any future tuning: this model is systematically harsh on form substitutions, returning `UNFAITHFUL` at 800–1500bp for most same-base form changes. That is a property of the model, not of the gate, and it is one reason a second provider behind the Protocol is worth having.

## Reproducing

```bash
.venv/bin/python -m eval.corpus.build      # regenerate; reviewed labels are preserved
.venv/bin/python -m eval.harness --split TEST
.venv/bin/python -m eval.sweep --split ALL --csv docs/sweep.csv
.venv/bin/pytest tests/test_corpus.py      # the corpus as a regression suite
```

The corpus runs in the test suite, so a change that alters a graded outcome fails the build rather than being noticed the next time someone happens to run the evaluation.

## Reviewing the labels again

A second reviewer is the most valuable thing anyone could add to this corpus, because the bounds in §"What the agreement is worth" are exactly what a second, independent pass would tighten.

```bash
python -m eval.corpus.review --sheet                       # the evidence, per case
python -m eval.corpus.review --apply --as you@example.com  # your calls, attributed
```

1. `--as NAME` is required to write a label: an unattributed judgment cannot be told apart from a relabelled draft (`BROKE.md` 010).
2. Ignore `decisions.txt` until you have made your own calls. It contains the current reviewer's reasoning and reading it first is the anchoring problem, deliberately.
3. `python -m eval.corpus.build` preserves reviewed labels across a regeneration, so a rebuild never silently reverts a judgment (`BROKE.md` 014).
4. Re-run the harness. Where two reviewers disagree is worth more than where either agrees with the gate.
