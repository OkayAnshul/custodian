# Decision log

Every engineering decision that would otherwise exist only in chat history.
Format is trimmed to the fields that carry weight; a field with nothing to say is omitted rather than filled with "none".

---

## ADR-001 — Money is integer paise

**Date** 2026-08-21 · **Area** core · **Status** Accepted

**Problem.** Every amount in this system can affect whether money moves. Representation errors here are not cosmetic.

**Options.** (1) `float` rupees. (2) `Decimal` rupees. (3) `int` paise.

**Chosen.** `int` paise. ₹2,000 is `200000`.

**Why.** Floats cannot represent ₹0.10 exactly, and — the decisive reason — they have no canonical byte form, so a float amount in a ledger payload makes the hash chain non-reproducible across platforms. `Decimal` is exact but still needs a serialisation convention (`1.5` vs `1.50` vs `1.5E+0` all round-trip differently), so it moves the problem instead of solving it. Integers have exactly one representation.

**Trade-off.** Every boundary needs an explicit parse and an explicit format. `money.parse_paise` and `money.format_inr` are the only two places that convert, and `_reject_float` makes the failure loud rather than silent.

**Security implication.** A float rounding difference between the price check and the settlement call is a real path to charging an amount the gate never approved. Integers remove the class.

---

## ADR-002 — Scores are integer basis points

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Problem.** Per-dimension scores are recorded in the ledger and re-derived during replay. A score of 0.85 has the same canonicalisation problem as a price of ₹0.85.

**Chosen.** Basis points, `0`–`10000`, in `custodian.bp`. All aggregation (`bp.weighted`, `bp.from_ratio`) stays in integer arithmetic with explicit half-up rounding.

**Why.** Four significant digits is more resolution than any threshold in this system needs, and it makes replay bit-exact rather than approximately-equal. A replay assertion written as `abs(a - b) < 1e-9` is not the same claim as "the same decision", and a judge is entitled to notice the difference.

**Trade-off.** Slightly noisier arithmetic at the call site. Worth it: `9200` and `0.92` cost the same to read, and only one of them is reproducible.

---

## ADR-003 — Floats are rejected by the serialiser, not rounded

**Date** 2026-08-21 · **Area** core · **Status** Accepted

**Chosen.** `canonical._validate` walks every payload and raises `CanonicalisationError` on any `float` or `Decimal`, naming the JSON path (`$.nested[1].deep`).

**Why.** ADR-001 and ADR-002 are only real if something enforces them. A convention that "we use paise" degrades the first time someone writes `score=0.85` at 2am on day 11. Rejecting at the serialiser means the failure happens at the write, with the path in the message, rather than as an unexplained replay mismatch on day 12.

**Rejected.** Coercing floats to the nearest int. That is a silent data change on the exact path where silence is most expensive.

---

## ADR-004 — Composite hashes cover a structure, never a concatenation

**Date** 2026-08-21 · **Area** ledger · **Status** Accepted

**Problem.** A chain link must commit to `prev_hash`, `event_id`, `request_id`, `ts`, `event_type` and `payload` together.

**Options.** (1) `sha256(prev + type + id + payload)`. (2) Length-prefixed concatenation. (3) `sha256(canonical({...}))`.

**Chosen.** (3).

**Why.** String concatenation is ambiguous at the field boundary: `event_type="AB", event_id="C"` and `event_type="A", event_id="BC"` produce identical bytes and therefore identical hashes. Length-prefixing fixes it but invents a second serialisation format to get right. Hashing a canonical object reuses the primitive that already exists and is unambiguous by construction.

---

## ADR-005 — Append-only is enforced by the database

**Date** 2026-08-21 · **Area** ledger · **Status** Accepted

**Chosen.** `BEFORE UPDATE` and `BEFORE DELETE` triggers that `RAISE(ABORT)` on the `ledger` table.

**Why.** "We only ever insert" is a convention, and a convention is not evidence. A database that refuses to mutate is a claim that survives being tested — and it *is* tested (`test_update_is_refused_by_the_database`). It also catches the accidental case, which is the likely one: a helper written on day 9 that "fixes up" a row.

**Trade-off.** Does not stop an attacker with file access, who drops the triggers first. That is the hash chain's job, and the tamper tests defeat the triggers deliberately to prove the chain still detects the edit.

---

## ADR-006 — Observed and inferred are separated in every payload

**Date** 2026-08-21 · **Area** ledger · **Status** Accepted

**Chosen.** Every ledger payload is `{"observed": {...}, "inferred": {...}}`, validated on append.

**Why.** The problem statement takes this discipline from Voyager's watchdog — log the data gap, do not interpolate across it. Left as prose it decays under time pressure. As a validated envelope it cannot be skipped, and `verify_chain` reports a payload that lost the shape as `MALFORMED_PAYLOAD`.

**What goes where.** `observed` — a catalog price, a gateway response, the JSON a model actually returned. `inferred` — a score, a confidence, an outcome. The distinction is what lets a dispute separate "the catalog said ₹199" from "we concluded this was a faithful substitution".

---

## ADR-007 — Substitution scoring by attribute decomposition, not lexical similarity

**Date** 2026-08-21 · **Area** gate · **Status** Accepted · **Deviates from problem statement §6**

**Problem.** §6 specifies "containment similarity, then LLM only on tie", citing Jaccard for identity and containment for membership.

**Context.** That primitive cannot separate §4's own flagship pair:

```
jaccard({coconut, milk}, {coconut, cream}) = 1/3 = 0.3333   -> faithful
jaccard({coconut, milk}, {almond,  milk })  = 1/3 = 0.3333   -> not faithful
containment gives 0.5 for both.
```

Identical scores, opposite ground truth. Under §6 as written both land in the tie band and the LLM decides both — so the deterministic layer contributes nothing on exactly the cases the project exists to decide, while §6's argument claims the opposite.

**Options.** (1) Build §6 verbatim. (2) Attribute decomposition into `(base, form, category)`. (3) Lexical first, attributes as tie-breaker.

**Chosen.** (2). Ingest emits `(base, form, category)` per item. Base mismatch is a deterministic fail; base match with the form pair present in a hand-authored compatibility table is a deterministic score; only unlisted form pairs, bundle equivalences and `base=UNKNOWN` escalate.

**Why.** Both flagship cases resolve deterministically with reason codes that write themselves — `SUBST_BASE_CHANGED`, `SUBST_FORM_COMPATIBLE`. The LLM's remaining job (one paste jar ≡ three spices) is genuinely the case language understanding is required for, which makes §6's "two model positions" argument *stronger* rather than a claim the code does not support. `base=UNKNOWN → escalate → hold` also makes calibrated abstention fall out of the design instead of being bolted on.

**Trade-off.** Requires a hand-curated lexicon sized to one merchant's catalog (~150 items) plus two versioned data files. That authoring effort is real — and it is the same India-specific judgment §9 already argues is what makes the project hard to copy.

**Rejected.** (3) — two scoring systems to build, tune and explain, to keep a sentence in a document literally true.

---

## ADR-008 — The payment provider sits behind a Protocol from day 1

**Date** 2026-08-21 · **Area** payments · **Status** Accepted

**Context.** The Razorpay account did not exist when the build started. Day 5's checkpoint (agent buys, payment settles) is non-negotiable, and signup latency is not under our control.

**Chosen.** A four-method `PaymentGateway` Protocol. `FakeGateway` and the forthcoming `RazorpayGateway` both satisfy it and both must pass `tests/contract/test_payment_gateway.py` unchanged.

**Why.** It makes signup latency a scheduling risk instead of a blocking one — the gate, ledger, eval harness and demo can all be built and verified against the fake. It also means that when live credentials land, a failure is unambiguously a credential or API-shape problem, because the logic already passed the identical suite.

**Operational note.** `FakeGateway` is not a mock. It enforces idempotency and single-capture itself, so a settlement bug fails locally rather than surfacing for the first time against a live endpoint.

---

## ADR-009 — Idempotency key and single-capture are two separate controls

**Date** 2026-08-21 · **Area** payments · **Status** Accepted

**Problem.** "Do not pay twice" has two distinct failure modes.

**Chosen.** Both, enforced in the gateway contract. An idempotency key protects a *retry* of the same call: replaying a key returns the original result, and reusing it with different arguments raises `IdempotencyConflict`. Order-level single-capture protects against two *different* calls moving money for one order: a second capture raises `AlreadyCaptured` even under a fresh key.

**Why.** The first control alone is bypassed by an untrusted client that simply generates a new key — which is precisely the threat model. A control an agent can walk around by changing one string is not a control.

---

## ADR-010 — `gate.decide()` is pure; model output is a recorded observation

**Date** 2026-08-21 · **Area** gate, ledger · **Status** Accepted

**Problem.** §5.5 promises decisions replayable from the ledger without calling a model. §6 puts an LLM inside the decision path. As stated these conflict, and it is the first thing a technical judge will press on.

**Chosen.** The model runs *upstream* of the decision. Its constrained JSON verdict is written to the ledger as an `observed` input — the same status as a catalog price or a gateway response. `decide(intent, cart, snapshot, mandate, semantic_verdicts, thresholds)` is a pure function: no clock, no network, no randomness, no dict-order dependence. Replay reads the recorded verdicts and re-runs `decide()`.

**Why.** It resolves the conflict without weakening either claim. The model genuinely participates in the decision; the decision is genuinely reproducible, because what the model returned is evidence rather than an oracle to re-consult. It also makes the model's non-authority literal rather than rhetorical — `decide()` cannot call it even if someone wanted to.

**Enforcement.** A replay test asserts byte-identical output across the whole corpus, with a model client mocked to raise if touched.

---

## ADR-011 — SQLite, not Postgres

**Date** 2026-08-21 · **Area** storage · **Status** Accepted

**Chosen.** SQLite in WAL mode, one file.

**Why.** One merchant, single-process, and the ledger's requirements are append-only writes plus ordered reads. Postgres buys concurrency and operational maturity this project has no use for, and costs a service to run during a demo. `BEGIN IMMEDIATE` on append takes the write lock before reading the head, so concurrent appenders cannot fork the chain — the one concurrency property that actually matters here.

**Trade-off.** Does not scale past a single writer. Stated as a limitation rather than papered over; the migration path is that `Ledger` is the only thing that touches SQL.

---

## ADR-012 — Python, not Kotlin

**Date** 2026-08-21 · **Area** stack · **Status** Accepted

**Context.** Author's demonstrated depth is Kotlin — three shipped apps, 1,200+ tests. The submission is judged on running.

**Chosen.** Python 3.12+, FastAPI, Pydantic.

**Why.** Pydantic models *are* the data contracts, so schema-first costs nothing extra. The corpus tooling, threshold sweep and eval harness are data work that Python does in a fraction of the lines — and those are the days that would otherwise come out of the substitution scorer, which is the one component that is not plumbing. First-party SDKs exist for both Razorpay and Anthropic.

**Trade-off.** The submission repo does not showcase the Kotlin record. That record is panel-round material; the submission's job is to get into the room by running.
