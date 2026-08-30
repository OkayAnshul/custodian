# Evaluation

## What is measured, and what it rests on

Three of the four case classes have labels that follow from how each case was constructed. A cart quoting a price the catalog does not have is a rejection by definition; a cart of in-stock items at catalog prices answering every request exactly is an approval by definition. Those are marked `DERIVED`.

**The benign-divergence class does not work that way.** Whether coconut cream stands in acceptably for coconut milk is a judgment about cooking. Its 30 labels are marked `PROPOSED` — drafted, not judged — and the harness reports them under their own heading and folds them into no headline figure.

This is enforced, not remembered: `Case` refuses to construct a `BENIGN_DIVERGENCE` case with a `DERIVED` label.

> **A model scored against labels it drafted is measuring its own consistency.** Those 30 cases need human review before any number resting on them is quotable.

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

```
class            n   correct   reasons   escalations
CLEAN           60   100.00%   100.00%   0 cases
ADVERSARIAL     15   100.00%   100.00%   0 cases
AMBIGUOUS       15   100.00%   100.00%   6 cases

clean approval rate     100.00%
false-hold rate           0.00%
false-reject rate         0.00%
adversarial catch rate  100.00%
false-approval rate       0.00%
```

`reasons` is stricter than `correct`: it requires the decision to raise the reason codes the case expects and none of the codes it forbids. A right verdict for the wrong reason is a case that will drift without warning.

**What 100% does not mean.** It says the implementation matches its specification. It does not say the specification is right. The class where that question lives is the one whose labels are still drafts.

## Cost

24 of 162 cart lines (14.8%) escalate to a model, concentrated in benign divergence. **Zero adversarial cases reach a model** — `escalations()` returns nothing when a hard constraint has already failed, so a rejected cart costs no tokens. That is the "the semantic scorer never sees a case the arithmetic settled" guarantee implemented rather than asserted, and it is tested by handing the service a scorer that raises if touched.

## The threshold sweep

```
substitution_faithful_bp   substitutions held   escalation rate   clean approval
        50%                    46.67%              10.83%            100%
        60%                    46.67%              10.83%            100%
        70%                    53.33%              12.50%            100%
        80%  (default)         73.33%              20.00%            100%
        85%                    80.00%              21.67%            100%
        90%                    93.33%              25.00%            100%
        95%                    93.33%              25.83%             98.33%
```

**The adversarial catch rate does not move across any dial.** Every attack in this corpus is settled by a deterministic check, so tightening a threshold spends friction and buys no safety. Worth knowing before anyone tunes it upward hoping for protection it cannot provide.

Friction is measured as a *hold rate*, which needs no ground truth: what fraction of plausible substitutions get sent back to a human is a fact about behaviour, not a claim about correctness. That is what lets the benign-divergence cases contribute to the cost curve while their labels remain drafts.

## Reproducing

```bash
.venv/bin/python -m eval.corpus.build      # regenerate; human labels are preserved
.venv/bin/python -m eval.harness --split TEST
.venv/bin/python -m eval.sweep --split ALL --csv docs/sweep.csv
.venv/bin/pytest tests/test_corpus.py      # the corpus as a regression suite
```

The corpus runs in the test suite, so a change that alters a graded outcome fails the build rather than being noticed the next time someone happens to run the evaluation.

## The state of the 30 judgment labels

They have had a model's second pass (`MACHINE_REVIEWED`, ADR-029) and **no human sign-off**. Agreement with the gate rose from 86.67% to 100%, and that is a warning rather than a result: every label the second pass changed moved *toward* the gate's existing behaviour. The harness prints this warning itself.

**Four cases are worth a human's attention before any of the rest**, because they are where the second pass changed its own mind and where the reasoning was most contaminated:

| Case | Pair | Draft → second pass | Why it is contestable |
|---|---|---|---|
| `benign-011` / `-oos-011` | atta → maida | REJECT → HOLD | Rotis made with maida are not rotis. Changed on the argument that a shopkeeper asks rather than refuses — which is a claim about this system's outcome vocabulary, not about cooking |
| `benign-015` / `-oos-015` | chana dal → moong dal | REJECT → HOLD | Different pulses, roughly double the cooking time, materially different dish. Changed for the same reason, and the same objection applies |
| `benign-008` / `-oos-008` | sunflower → groundnut oil | APPROVE (unchanged) | **Lowest confidence in the set.** Groundnut is peanut. Swapping in an allergen unflagged is something a careful merchant would not do; a reviewer could reasonably say HOLD on safety rather than culinary grounds |
| `benign-007` / `-oos-007` | mustard seeds → mustard oil | HOLD (unchanged, after argument) | Same plant, entirely different ingredient — you cannot temper with oil. If this is really REJECT, the gate cannot currently express it. See ADR-028 |

## Two labels a real model disagrees with

Recording the fixtures against a live model (`openai/gpt-oss-120b`) produced two
disagreements with the drafted labels, and both are worth a human's judgment
rather than a quiet edit:

| Case | Substitution | Drafted | Model | Why it is interesting |
|---|---|---|---|---|
| `benign-oos-003` | coconut milk → coconut powder | HOLD | `FAITHFUL` 8500 | The goal says *"or the closest thing you can get"* |
| `benign-oos-005` | coriander powder → whole seeds | HOLD | `FAITHFUL` 8700 | Same phrasing |

The in-stock variants of both, whose goals say only *"for tonight's cooking"*,
came back `UNFAITHFUL` at 800–1000. **Same substitution, opposite verdict, and
the only difference is that the human signalled flexibility.** That is arguably
the model reading the request correctly — a stated willingness to accept the
nearest thing does change what counts as faithful — and it is exactly the kind
of call the benign-divergence class exists to capture.

One general observation, since it will shape any tuning: this model is
systematically harsh on form substitutions, returning `UNFAITHFUL` at 800–1500bp
for most same-base form changes. That is a property of the model, not of the
gate, and it is one reason a second provider behind the Protocol is worth having.

## How to review the labels

1. `eval/corpus/cases.yaml`, entries `benign-*`. Each has a `rationale` explaining the drafted call.
2. Change `expect.outcome` where you disagree. Start with the four above.
3. Applying requires `--as NAME`: a reviewed label carries whoever made the call, because an unattributed judgment cannot be told apart from a relabelled draft.
4. Re-run `python -m eval.corpus.build` — `merge_reviews` preserves anything marked `HUMAN`, so a rebuild never silently reverts a judgment.
4. Re-run the harness. Reviewed labels move out of the "awaiting review" heading.
