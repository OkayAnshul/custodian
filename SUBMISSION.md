# Submission draft

Answers for the application form. Edit freely — these are drafted to be pasted, not to be admired.

---

**Track**
01 — AI Growth & Agentic Commerce

**Project name**
Custodian

**Repository**
https://github.com/OkayAnshul/custodian

---

## What it solves

The agentic commerce stack proves an agent was *permitted* to spend — AP2, and UAP in India — but no layer checks whether it bought what the human actually asked for. That gap lands on the merchant: Razorpay's own position is that if an agent orders the wrong item, the merchant handles the dispute.

Custodian is a merchant endpoint that makes a store transactable by any AI buyer and then treats that buyer as an untrusted client — re-deriving price, purpose and mandate fit server-side, gating three ways with calibrated abstention, and emitting a hash-chained trail a dispute can be resolved from.

The hard part is one question: *does this cart satisfy this intent?* Coconut milk is out of stock — coconut cream is a faithful substitute, almond milk is not, and lexical similarity scores them identically at 0.3333. Custodian decomposes every product into base ingredient and form against a hand-authored Indian grocery lexicon, so both cases are decided by arithmetic with no model involved.

---

## How it works

Messy merchant CSV in — transliterated Hindi pack sizes, prices inside item names, six spellings of "in stock" — normalised to a content-hashed catalog snapshot. The buying agent submits a schema'd intent alongside its cart. Before money moves, six deterministic checks re-derive price, budget, merchant scope, category, mandate fit and sanitizer state, and reject on their own authority. Only survivors reach substitution scoring; only genuine ties reach a model.

Eight dimensions, scored separately, each with reason codes. Three outcomes: approve, hold, reject. Hold routes to re-confirmation and a legitimate purchase still completes — and re-confirmation does not rewrite the decision, because "held, then a human overrode it at 14:32" is the truthful record and it is the number a false-hold rate is measured from.

Every decision replays byte-for-byte from the ledger with the model client mocked to raise if called.

---

## AI judgment — where a model is and is not used

Two positions, both deliberate: parsing natural-language intent, and breaking substitution ties the attribute tables cannot. Everything else is integer arithmetic, set membership and table lookup.

Measured: **24 of 162 cart lines reach a model. Zero adversarial cases do** — deterministic checks settle them first, so a rejected cart costs no tokens.

Both positions have two implementations behind one Protocol — Claude and Groq — and a test asserts the same substitution through either scorer produces a byte-identical `Decision`. The answers the default path replays are 28 real recordings from `openai/gpt-oss-120b`, stored with prompt digest and provenance, not fixtures I wrote.

No vector store, no RAG, no agent framework. The sanitizer is rules rather than a classifier, partly for cost and partly because a classifier trained on our own adversarial fixtures and scored on the same corpus would be circular.

---

## Evidence

- **549 tests**, 13 running against the live Razorpay test-mode API on every run with credentials present — the gateway contract suite, and the hosted checkout page rendered against an order Razorpay actually issued.
- **120-case corpus**, four classes, DEV/TEST split, each case with a written rationale. Clean approval 100%, adversarial catch 100%, false-approval 0% on the TEST split.
- **Threshold sweep**, because a single score at one threshold is an assertion. Raising the substitution bar from 50% to 95% sends 46.67% → 93.33% of plausible substitutions back to a human and raises model cost by half — and the adversarial catch rate does not move at all, because those are settled deterministically.
- **Runs from a clean clone with no credentials**: `make install && make demo`.

**Stated plainly:** the UPI mandate is modelled, not integrated — Reserve Pay is not reachable from a self-serve test account. Order creation, the payable link, fetch and capture are live Razorpay calls, and a live test renders the hosted page against a real order; completing a payment still needs a person with a card, and that browser leg is the one part of the loop nothing here has walked. And 30 corpus labels are the kind that need cooking judgment; they have had a model's second pass and no human sign-off, and no headline number rests on them.

---

## Field 12 — what broke and how you got out

Fourteen entries in `BROKE.md`, written as they happened. Four worth the space, a fifth that matters more than any of them, and two more found on the last pass before submitting:

**The gate approved an order with a failed dimension.** Almond milk offered for coconut milk scored 34% on substitution, and seven passing dimensions carried the weighted mean to 85%, so it approved — the exact failure the project exists to prevent. I had written *"a constraint that can be outvoted by a good average is not a constraint"* as a comment inside the function where precisely that happened.

Fixed structurally rather than by re-tuning weights: any dimension at `FAIL` or `UNCERTAIN` caps the outcome at hold. Weights decide how much a dimension *contributes*; they do not decide whether a failure *counts*. A blocking-code list depends on someone registering each new code; a status rule covers dimensions that do not exist yet. The test asserts both halves — that the aggregate still reads above the approve threshold, *and* that it still cannot approve — because a test checking only the outcome would pass again if someone later tuned the weights until the average dipped.

**The payment interface described a provider that does not exist.** It had `create_order` then `capture(order)`. Razorpay is `order → a human pays → authorized payment → capture`, and an unpaid order has zero payments on it. My fake had been passing the full contract suite, through every phase of the build to that point, against an API I had imagined. A fake that satisfies a contract the real thing cannot is worse than no fake: it converts an unknown into false confidence. The spike was scheduled first because this was the riskiest unknown, and it stayed unknown until real credentials forced the question, because a green suite felt like evidence.

**The first real model answers broke the abstention guarantee.** Until the fixtures were recorded, every model response the suite ran on was one I had written. Recording 28 real ones cost one command, and the first run with them flipped the case that exists to demonstrate calibrated abstention: an item the taxonomy cannot place at all went from `HOLD` to `APPROVE`, because the model was asked whether "Sparkle Glitter Pens 5 nos" substitutes for "glitter pens" and said `FAITHFUL` at 95%. That answer is correct. My fixture had said `UNSURE`, which preserved the behaviour I expected and hid the bug for the whole build. The category error was mine: `base=UNKNOWN` does not mean "these might be unalike", it means the taxonomy could not place the item — and a verdict about similarity cannot supply that. **A model can tell you two things are alike; it cannot tell you what they are.** The substitution dimension now holds at `UNCERTAIN` whenever a line carried `SUBST_BASE_UNKNOWN`, whatever the verdict says.

**I defeated my own integrity control.** The corpus separates labels that follow from construction from labels that need human judgment, and the second kind are meant to stay marked as drafts. Testing the review tool, I wrote three made-up calls to watch the round-trip work, rebuilt, and the merge logic correctly preserved them — leaving three labels I had invented, marked as human-reviewed, inside the one class whose whole design exists to keep machine labels out of the numbers. The provenance field recorded *whether* a judgment was made, not *whose*. A reviewed label now names its reviewer and the schema refuses an unattributed one.

**I fabricated the project timeline.** The engineering log carried nine dated entries spread across 21–29 August. Every commit in the repository is timestamped 21 August — the whole build was four sittings in one day. I had labelled each phase with the calendar date the plan assigned it rather than the date it happened, in the past tense, and once the first heading was written that way the rest followed without the question being asked again. Found by comparing the log against `git log`, which cost one command, and which I only ran because someone asked whether things were working.

Corrected: headings now name the plan phase and the real sitting, and a note at the top of the log states the compression outright. This is the worst entry in the file. Everything Custodian claims rests on its evidence being honest — that a number was measured, that a decision replays because it was tested, that a drafted label is marked as drafted. A fabricated timeline in the same repository gives a reader a reason to discount all of that, including the parts that are carefully true.

Two more, found in the pass where I ran every demo path against live credentials rather than trusting the suite. The payable link had worked exactly once — Razorpay's `reference_id` on a link is a uniqueness constraint, not an idempotency key — so the demo printed `link unavailable` on every run after the first, and a failure that only appears on the *second* run is invisible to a suite that starts clean every time. And the build had been red for ten runs: every step passed except the one comparing the committed corpus against a fresh build, which could never pass, because a rebuild dropped the machine-reviewed labels. A check that cannot pass looks exactly like a check that always fails, and after the second red run I stopped reading it.

Two through-lines. In the gate and the integrity control, I had reasoned correctly about a failure mode and, having named one, stopped looking for the neighbouring one. The model fixture is the payment fake in a different costume — a stand-in written by the person who also wrote the expectations agrees with them, and it is not a test until something I did not author has a chance to disagree. The timeline is a different failure and a worse one: not a gap in reasoning but a plan quietly transcribed as a record, which is how most fabricated evidence actually gets made.

---

## What I deliberately did not build

Retry routing is Optimizer. Chargeback evidence is the Dispute Auto-Responder. Mandate caps are Reserve Pay. Most obvious ideas in this track are a worse version of something shipped last quarter, so Custodian *consumes* the mandate as an input and *emits* what a dispute responder would need.

No multi-merchant, no auth, no dashboard, no vector database. Reaching for LangChain here would actively cost points on AI judgment — the deterministic core is the argument.
