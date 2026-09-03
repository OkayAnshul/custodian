# Custodian

**Custodian makes an Indian merchant transactable by an AI buyer end to end — and then treats that buyer as an untrusted client.**

Two halves, both measured.

**Transactable.** A merchant with unusable product data is invisible to agents however good the checkout is. Of 70 rows in a real kirana export, an AI buyer can act on **18** — the rest are missing a readable price, a matchable identity, or a stock signal it can evaluate, and none of them carry a pack size as its own field. After ingest: **69 of 70**.

**Untrusted.** Every claim the agent makes — price, item, authority — is re-derived server-side before money moves. Across a 120-order corpus:

```
₹41,609  would settle unchecked, at the prices the agent asserted
₹12,063  Custodian let through, at catalog prices
₹31,655  stopped or held for a human — 72% of value
 ₹2,109  price the agent forged
₹13,720  items nobody asked for: inside budget, correctly priced, still wrong
      0  of 60 clean orders held. Zero friction.
```

Every one of those numbers is printed by `make money`.

> **Why this and not a guardrail.** A guardrail inspects text and guesses. Custodian re-derives against a catalog it controls and a mandate with hard numbers, gates three ways with calibrated abstention, and writes a hash-chained trail a dispute can be resolved from. Different mechanism, different failure surface.
>
> **Why this and not Vulcan.** Razorpay's payments foundation model asks whether the payment is *genuine* — routing, fraud, risk, across four billion payments. Custodian asks whether the purchase was *what was asked for*. Different question, and nothing in the stack was answering it.

---

## 1. The problem

The agentic commerce stack settled into four layers during 2025–26. Three of them are solved or being solved:

| Layer | What it answers | Standards |
|---|---|---|
| Communication | How does the agent talk to systems? | MCP, A2A |
| Commerce | How does it discover a catalog and build a cart? | UCP, ACP |
| Authorization | Was the agent *permitted* to spend? | AP2, and in India NPCI's UAP |
| Settlement | How does value move? | x402, MPP; in India UPI |

**There is no purpose layer.** AP2 proves a human mandated the spend within limits. It does not ask whether the cart matches the request. UAP is built the same way — NPCI's role stops at verifying that a payment request is genuine, without visibility into what is being purchased.

That is not an oversight. It is a deliberate scope boundary at the rail, which means the check has to happen somewhere else: at the merchant and its aggregator.

**And the liability is already assigned, on a product that is live.** Razorpay and Sarvam shipped a voice agent that completes payments without a PIN, with **Swiggy** as the launch partner. Razorpay's stated position: *"the introduction of agentic shopping does not rewrite the rules of commercial liability."* Commercial disputes sit with the merchant; payment security sits with Razorpay.

So when that agent orders the wrong thing, Swiggy handles the dispute and the refund. The merchant now transacts with a counterparty they did not build, running on content they do not control, with no tooling to evaluate any given order. This is not a problem arriving later — it shipped in March.

Agentic commerce asks whether this is the right agent, for the right person, under the right authorization, **for the right purpose**. The first three are handled. The fourth is open.

---

## 2. The hard part

Everything except one component is plumbing. That component is: **does this cart satisfy this intent?**

Consider *"ingredients for a Thai curry, under ₹2,000."* Coconut milk is out of stock.

| The agent… | Verdict |
|---|---|
| substitutes coconut cream | faithful |
| substitutes almond milk | not faithful |
| substitutes one curry paste jar for three separate spices | arguably faithful |
| adds a ₹400 wok because the recipe mentions one | out of scope, within budget |
| buys the right items from a merchant the user never named | authorized, wrong |

There is no library for this and no benchmark.

### The primitive the obvious approach reaches for does not work

Lexical similarity is the natural first idea, and it cannot decide the example above:

```
jaccard({coconut, milk}, {coconut, cream}) = 1/3 = 0.3333   ->   faithful
jaccard({coconut, milk}, {almond,  milk }) = 1/3 = 0.3333   ->   not faithful
```

Identical scores, opposite ground truth. Containment gives 0.5 for both. A test asserts this, so the premise is checkable rather than argued.

**Custodian decomposes instead.** Every product — in the catalog and in the request — is reduced to `(base, form, category)` against a hand-authored lexicon, and substitution is scored on identity first, then shape:

```
coconut milk -> coconut cream    base coconut == coconut, form pair milk~cream = 8500   FAITHFUL
coconut milk -> almond milk      base coconut != almond, no recorded relationship       REJECT
```

Both decided deterministically, with reason codes, **without calling a model**. The model is left the cases that genuinely need language understanding — an unlisted form pair, a bundle, an ingredient the taxonomy cannot place.

---

## 3. Three design commitments

**Graded, not binary.** Satisfaction is a continuous score. The hold threshold is a tunable parameter with a measured cost curve, which turns the evaluation into an argument instead of a pass rate.

**Calibrated abstention.** The gate must know when it does not know. Low-confidence decisions route to `hold`, never to a guess. Confidence is *computed* from evidence coverage and threshold margin — never a model's self-report, which correlates with fluency rather than accuracy.

**Decomposed scoring.** Alignment is not one number. Eight dimensions are scored separately, each with its own reason codes. Explainability is a byproduct of decomposition, not a feature bolted on top.

---

## 4. Architecture

```
messy catalog ──► ingest ──► sanitize ──► snapshot(hash) ──► agent feed
                                                                  │
human intent ──► naive buyer agent ──► structured intent + cart ──┘
                                                    │
                                    ┌───────────────▼─────────────────┐
                                    │ deterministic — can reject alone │
                                    │ price · budget · merchant ·      │
                                    │ category · mandate · sanitizer   │
                                    └───────────────┬─────────────────┘
                                                    │ survivors only
                                    ┌───────────────▼─────────────────┐
                                    │ binding: cart line → intent item │
                                    │ substitution: base/form/category │
                                    │ scope creep: unbound cart value  │
                                    └───────────────┬─────────────────┘
                                          ties only │
                                    ┌───────────────▼─────────────────┐
                                    │ LLM #2 — strict JSON verdict     │
                                    │ recorded, not authoritative      │
                                    └───────────────┬─────────────────┘
                                                    ▼
                                       decide() ── PURE ──► approve │ hold │ reject
                                                    │
                                    hash-chained ledger ──► replay viewer
                                                    │
                                            approve ▼
                                        Razorpay test-mode settlement
```

### Trust model

| Party | Trusted for | Never trusted for |
|---|---|---|
| Human | the intent, and re-confirming a hold | — |
| Buying agent | proposing a cart | prices, item identity, scope, its own binding claims |
| Merchant catalog | prices and stock | the text inside its own descriptions |
| Payment mandate | spending authority | whether the purchase was what was asked for |
| Model | reading language, breaking substitution ties | any money-affecting decision |

The agent's cart carries `asserted_unit_price_paise` — the only price-bearing field on the type, named so that trusting it looks wrong. A test asserts no naked `price` field exists.

---

## 5. Where I chose not to use a model

*The stated bar for the Open Track is "meaningful use of AI." This is the answer to it: meaningful means placed where it is load-bearing, and absent where a lookup is strictly better. The table is the argument, so it is stated in full rather than summarised.*

| Task | Tool | Why |
|---|---|---|
| Price verification | Integer comparison | A model would be strictly worse and non-deterministic |
| Budget / mandate arithmetic | Plain arithmetic | Must be auditable and reproducible from the ledger |
| Merchant + category scope | Set membership | A stated rule, not a probability |
| Unit normalization | Rules + lookup table | `250gm` = `1/4 kg` is a parsing problem, not a reasoning one |
| Item substitution fidelity | Attribute decomposition, then LLM only on tie | Base identity and form compatibility are lookups; only the unlisted pairs need judgment |
| Ambiguous natural-language intent | LLM, once, at parse time | The only place language understanding is genuinely required |
| Sanitizer triage | Rules | Runs on every ingest; must be cheap. A classifier trained on our own fixtures and scored on the same corpus would be circular |

**And the model is a component, not the system.** *Both* positions have two implementations — `ClaudeParser`/`GroqParser` and `ClaudeScorer`/`GroqScorer` — each pair behind one Protocol and graded by one contract suite. A test runs the same substitution through both scorers and asserts the resulting `Decision` is **byte-identical**, which is possible because the model id lives on the verdict rather than on the decision. Swap the provider; the decisions still replay.

A consequence worth stating: **the whole system runs on a free tier.** `make demo-groq` needs one `GROQ_API_KEY` and no paid account. That is not a cost argument — it is the swappability claim being cashed.

**The LLM occupies exactly two positions**: intent parsing, and substitution ties the deterministic layer cannot break. Measured across the 120-case corpus: **24 of 162 cart lines (14.8%) escalate to a model**, concentrated in the benign-divergence class where they belong. **Zero adversarial cases reach a model** — the arithmetic settles them first, so a rejected cart costs no tokens. Among the classes with derived labels, 6 of 90 cases escalate.

**And the answers being replayed are real ones.** 28 responses — 24 substitution verdicts and 4 intent parses — were recorded from `openai/gpt-oss-120b` on Groq and stored with provider, model, prompt digest and the question as sent. The first run against them broke an abstention guarantee that my own hand-written fixtures had preserved for the whole build (`BROKE.md` 012), which is the argument for recording them: a stand-in written by the person who also wrote the expectations agrees with them.

Every money-affecting decision is re-runnable from the ledger without calling a model. That reproducibility is the point — an audit trail you cannot replay is decoration.

---

## 6. Results

120 hand-built cases across four classes. Thresholds are chosen on DEV and reported on TEST; the splits are disjoint and stratified.

```
class            n   correct   escalations
CLEAN           60   100.00%   0 cases
ADVERSARIAL     15   100.00%   0 cases
AMBIGUOUS       15   100.00%   6 cases

clean approval rate     100.00%    does it get out of the way?
false-hold rate           0.00%    clean orders sent back to a human
adversarial catch rate  100.00%    does it work?
false-approval rate       0.00%    attacks that got through
```

**What that number does not mean.** Those three classes have labels that follow from how each case was built — a forged price is a rejection by construction. Scoring 100% says the implementation matches its specification. It does not say the specification is right.

**The class where that question lives is benign divergence.** Its 30 labels have had a model's second pass and no human sign-off, so they are reported separately and folded into no headline figure.

That second pass is itself worth reading as a result. Agreement with the gate rose from 86.67% to 100% — and every label it changed moved *toward* the gate's existing behaviour, reached by reasoning about what `REJECT` means *in this system* rather than about cooking. **The lower number was the more informative one.** The harness now warns when this agreement exceeds 95%, because near-total agreement between a model's labels and a model-built gate measures consistency rather than correctness. `EVALUATION.md` names the four cases a human should look at first.

### What it is worth, and what it costs

```
₹41,609  would settle unchecked, at the prices the agent asserted
₹12,063  Custodian let through, at catalog prices
₹31,655  stopped or held for a human — 72% of value
 ₹2,109  price the agent forged
₹13,720  items nobody asked for: inside budget, correctly priced, still wrong
      0  of 60 clean orders held — 0.00% friction
     24  of 162 cart lines needed a model at all — 14.81%
```

`make money`. The forgery figure is not a separate measurement: asserted plus forged equals the catalog total exactly, and a test asserts it, so the three cannot drift apart.

### The threshold sweep — the curve, not a point

```
substitution_faithful_bp   substitutions held   escalation rate   clean approval
        50%                    46.67%              10.83%            100%
        80%  (default)         73.33%              20.00%            100%
        95%                    93.33%              25.83%             98.33%
```

The adversarial catch rate **does not move across any dial**. Every attack in this corpus is settled by a deterministic check, so tightening a threshold spends friction and buys no safety. That is worth knowing before anyone tunes it upward hoping for protection it cannot provide.

---

## 7. Running it

```bash
make install                           # or: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
make test                              # 548 tests, +13 with Razorpay credentials
make demo                              # all six demo scenarios
make eval sweep                        # the corpus and the threshold curve
make serve                             # http://127.0.0.1:8000

# or directly:
.venv/bin/pytest                       # 548 tests
.venv/bin/python -m eval.harness --all # the corpus
.venv/bin/python -m eval.sweep         # the threshold curve
.venv/bin/python scripts/demo.py       # all six demo scenarios
```

Live Razorpay settlement needs test-mode credentials in `.env`:

```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

Thirteen tests then run against the live API — the payment-gateway contract suite, and the checkout page rendered against an order Razorpay actually issued. `RazorpayGateway` refuses any key not beginning `rzp_test_` at construction — the gate is not calibrated, and a live key here would move real money on a decision the project does not claim is tuned.

---

## 8. What I deliberately did not build

| Considered | Why not |
|---|---|
| Failed-payment retry / smart routing | Optimizer, and now Vulcan — a payments foundation model on 3 trillion data points |
| Subscription recovery | Shipped: Subscription Recovery Agent |
| Chargeback evidence responder | Shipped: Dispute Auto-Responder, in Agent Studio |
| Reconciliation / bookkeeping | Shipped: Bookkeeping Agent |
| RTO / return-risk scoring | Shipped: RTO Shield — LLM address validation plus bad-pincode intelligence, blocking high-risk COD before it ships |
| Mandate enforcement | Shipped: UPI Reserve Pay |
| Conversational checkout | Shipped: Agentic Payments on ChatGPT and Claude |
| Vector DB / RAG / agent framework | Reaching for LangChain or a vector store would actively cost points on AI judgment. The deterministic core is the argument |

Custodian **consumes** the mandate as an input and **emits** what a dispute responder needs. Complementary by construction.

---

## 9. Known limitations

Stated plainly, because a reviewer will find them anyway and the honest version is shorter.

- **The UPI mandate is modelled, not integrated.** Reserve Pay is not reachable from a self-serve test account. The mandate is constructed locally and checked deterministically. What this demonstrates is the layer *above* the mandate.
- **Completing a payment needs a human.** Order creation, the payable link, fetch and capture are live Razorpay test-mode calls and the payment ids in the ledger are Razorpay's, but no API call makes a payment *happen*. `GET /checkout/{request_id}` serves the page a payer completes it on; a live test asserts that page carries the order Razorpay issued, the derived amount, and the callback path, and six more cover the signature check that makes the browser's word evidence. **What is still unrun is the browser leg itself** — Razorpay's script and a person with a test card — and `LIMITATIONS.md` says so rather than claiming otherwise.
- **30 corpus labels are drafts.** See §6. `python -m eval.corpus.review --sheet` lays out the evidence for each; applying a call requires `--as NAME`, because a reviewed label with nobody's name on it cannot be told apart from a relabelled draft.
- **The lexicon covers one merchant.** 56 bases, 24 form-compatibility pairs, 5 base equivalences, sized to a 70-item catalog. Coverage against a different merchant is unmeasured.
- **Single writer.** SQLite, one process. `Ledger` is the only thing that touches SQL, so the migration path is contained.
- **Thresholds are `v0-untuned`.** The sweep says what tuning them would cost; nobody has tuned them.
- **The buyer agent is deliberately naive.** It matches lexically — the primitive the gate rejects — so it will offer almond milk for coconut milk. That is the point: the agent's failure and the gate's correctness come from one example.

---

## 10. The record

| Document | What it holds |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | 31 ADRs, each with the alternatives that were rejected |
| [`BROKE.md`](BROKE.md) | Fourteen failures, with root cause and what changed to prevent recurrence |
| [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md) | Session by session, written as it happened |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module map, contracts, ledger format, API |
| [`THREAT_MODEL.md`](THREAT_MODEL.md) | Ten threats, and the architectural control for each |
| [`EVALUATION.md`](EVALUATION.md) | The corpus, what it measures, and how to review the drafted labels |
| [`LIMITATIONS.md`](LIMITATIONS.md) | What is modelled, unfinished, out of scope, or deliberate |
| [`DEMO.md`](DEMO.md) | Four-minute script, every number produced live |
| [`DEFENSE.md`](DEFENSE.md) | Panel-round notes — the reasoning under each answer, not the answers |
| [`SUBMISSION.md`](SUBMISSION.md) | Form answers, drafted to be pasted |

`BROKE.md` is worth reading first. Five entries are the interesting kind:

- **007** — the gate approved an order with a *failed dimension*. Seven passing dimensions outvoted the one that mattered. I had written "a constraint that can be outvoted by a good average is not a constraint" as a comment inside the function where exactly that happened.
- **006** — the payment interface described a provider that does not exist. `FakeGateway` passed the whole contract, through every phase of the build, against an API I had imagined.
- **009** — the ledger could not be called from a web server. I had reasoned about concurrency correctly, about a different failure mode — and having named one, stopped looking.
- **011** — I fabricated the project timeline. The log recorded the dates the *plan* assigned to each phase rather than the dates work happened, spread across a week that had not occurred, while every commit was timestamped to one day. Corrected. It is the worst entry here, because everything else this project claims rests on its evidence being honest.
- **012** — the first run on *real* model answers broke the abstention guarantee. Asked whether "Sparkle Glitter Pens 5 nos" substitutes for "glitter pens", the model said `FAITHFUL` at 95% — which is correct — and an item the taxonomy could not place approved. My hand-written fixture had said `UNSURE`, so the bug was invisible for as long as the model's answers were mine. A model can tell you two things are alike; it cannot tell you *what they are*.
