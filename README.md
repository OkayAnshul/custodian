# Custodian

**The purpose layer for agentic commerce.** Make an Indian merchant transactable by an AI buyer end to end — then verify the agent bought what the human actually asked for.

> An "AI guardrail" inspects text and guesses. Custodian re-derives price, purpose and mandate fit against a catalog it controls and a mandate with hard numbers, gates three ways with calibrated abstention, and writes a hash-chained trail a dispute can be resolved from. Different mechanism, different failure surface.

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

**And the liability is already assigned.** Razorpay's public position on the Sarvam voice-agent launch is that agentic shopping does not rewrite commercial liability — if an agent orders the wrong item, the **merchant** handles the dispute and refund. So the merchant now transacts with a counterparty they did not build, running on content they do not control, with no tooling to evaluate any given order.

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

*Reproduced here because "AI judgment — the right tool in the right place, and where you chose not to use one" is a published criterion.*

| Task | Tool | Why |
|---|---|---|
| Price verification | Integer comparison | A model would be strictly worse and non-deterministic |
| Budget / mandate arithmetic | Plain arithmetic | Must be auditable and reproducible from the ledger |
| Merchant + category scope | Set membership | A stated rule, not a probability |
| Unit normalization | Rules + lookup table | `250gm` = `1/4 kg` is a parsing problem, not a reasoning one |
| Item substitution fidelity | Attribute decomposition, then LLM only on tie | Base identity and form compatibility are lookups; only the unlisted pairs need judgment |
| Ambiguous natural-language intent | LLM, once, at parse time | The only place language understanding is genuinely required |
| Sanitizer triage | Rules | Runs on every ingest; must be cheap. A classifier trained on our own fixtures and scored on the same corpus would be circular |

**The LLM occupies exactly two positions**: intent parsing, and substitution ties the deterministic layer cannot break. Measured across the 120-case corpus: **24 of 162 cart lines (14.8%) escalate to a model**, concentrated in the benign-divergence class where they belong. **Zero adversarial cases reach a model** — the arithmetic settles them first, so a rejected cart costs no tokens. Among the classes with derived labels, 6 of 90 cases escalate.

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

**The class where that question lives is benign divergence**, and its 30 labels are drafts. They are reported separately and folded into no headline figure, because a model scored against labels it drafted is measuring its own consistency. **Those 30 cases need human review before any number resting on them is quotable.**

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
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/pytest                       # 430 tests
.venv/bin/python -m eval.harness --all # the corpus
.venv/bin/python -m eval.sweep         # the threshold curve
.venv/bin/python scripts/demo.py       # all six demo scenarios
.venv/bin/uvicorn custodian.api.app:app --reload   # then open http://127.0.0.1:8000
```

Live Razorpay settlement needs test-mode credentials in `.env`:

```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

Twelve contract tests then run against the live API. `RazorpayGateway` refuses any key not beginning `rzp_test_` at construction — the gate is not calibrated, and a live key here would move real money on a decision the project does not claim is tuned.

---

## 8. What I deliberately did not build

| Considered | Why not |
|---|---|
| Failed-payment retry / smart routing | Razorpay Optimizer — ML routing across 150 parameters |
| Subscription recovery | Shipped: Subscription Recovery Agent |
| Chargeback evidence responder | Shipped: Dispute Auto-Responder |
| Reconciliation / bookkeeping | Shipped: Bookkeeping Agent |
| RTO / return-risk scoring | Shipped: RTO Shield |
| Mandate enforcement | Shipped: UPI Reserve Pay |
| Conversational checkout | Shipped: Agentic Payments on ChatGPT and Claude |
| Vector DB / RAG / agent framework | Reaching for LangChain or a vector store would actively cost points on AI judgment. The deterministic core is the argument |

Custodian **consumes** the mandate as an input and **emits** what a dispute responder needs. Complementary by construction.

---

## 9. Known limitations

Stated plainly, because a reviewer will find them anyway and the honest version is shorter.

- **The UPI mandate is modelled, not integrated.** Reserve Pay is not reachable from a self-serve test account. The mandate is constructed locally and checked deterministically. What this demonstrates is the layer *above* the mandate.
- **Completing a payment needs a human.** Order creation, the payable link, payment fetch and capture are live Razorpay test-mode calls, and the payment ids in the ledger are Razorpay's. But no API call makes a payment *happen* — a person completes it on a hosted page. Five contract tests skip on the live gateway for exactly this reason rather than pretending otherwise.
- **30 corpus labels are drafts.** See §6.
- **The lexicon covers one merchant.** 56 bases, 24 form-compatibility pairs, 5 base equivalences, sized to a 70-item catalog. Coverage against a different merchant is unmeasured.
- **Single writer.** SQLite, one process. `Ledger` is the only thing that touches SQL, so the migration path is contained.
- **Thresholds are `v0-untuned`.** The sweep says what tuning them would cost; nobody has tuned them.
- **The buyer agent is deliberately naive.** It matches lexically — the primitive the gate rejects — so it will offer almond milk for coconut milk. That is the point: the agent's failure and the gate's correctness come from one example.

---

## 10. The record

| Document | What it holds |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | 25 ADRs, each with the alternatives that were rejected |
| [`BROKE.md`](BROKE.md) | Nine failures, with root cause and what changed to prevent recurrence |
| [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md) | Session by session, written as it happened |

`BROKE.md` is worth reading first. Three entries are the interesting kind:

- **007** — the gate approved an order with a *failed dimension*. Seven passing dimensions outvoted the one that mattered. I had written "a constraint that can be outvoted by a good average is not a constraint" as a comment inside the function where exactly that happened.
- **006** — the payment interface described a provider that does not exist. `FakeGateway` passed the whole contract for four days against an API I had imagined.
- **009** — the ledger could not be called from a web server. I had reasoned about concurrency on Day 1, correctly, about a different failure mode — and having named one, stopped looking.
