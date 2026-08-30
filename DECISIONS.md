# Decision log

Every engineering decision that would otherwise exist only in chat history.
Format is trimmed to the fields that carry weight; a field with nothing to say is omitted rather than filled with "none".

Every decision below was made on **2026-08-21**, the single day this was built. An earlier version of this file spread the dates across 21–30 August to match the plan's day numbering; that was wrong and is corrected.

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

---

## ADR-013 — Contracts are strict, closed and frozen by default

**Date** 2026-08-21 · **Area** schemas · **Status** Accepted

**Problem.** Pydantic's defaults are wrong for a trust boundary in three ways, and all three are silent.

**Context.** Verified before building on it:

```
class Lax(BaseModel): amount: int
Lax(amount=199.0).amount   ->  199        # a float, coerced, silently
```

That walks a float straight past the integer-paise guarantee and into a ledger payload, where it has no canonical form (ADR-003). Default `extra="ignore"` means an untrusted client can attach arbitrary fields and have them dropped without trace. Default mutability means an object can change after it was hashed.

**Chosen.** `Contract` base sets `frozen=True`, `extra="forbid"`. `Paise`, `ScoreBp` and `Quantity` are `Field(strict=True)`.

**Why.** Each is a control, and a control that has to be remembered on every model is not a control. Strictness is targeted at numerics rather than set model-wide, so enums and timestamps still parse from JSON strings normally.

**Security implication.** `extra="forbid"` converts a silent drop into a visible rejection. An agent probing for accepted fields gets an error rather than an unremarked success.

---

## ADR-014 — One spelling of time, compared as instants

**Date** 2026-08-21 · **Area** core · **Status** Accepted

**Problem.** Timestamps here are compared (is this mandate live, is this snapshot stale) *and* hashed. ISO-8601 permits several spellings of one instant: `Z` and `+00:00`, `+05:30`, fractional seconds at any precision.

**Context.** Both uses break, and the comparison breaks silently:

```
'2026-08-22T00:00:00+05:30' > '2026-08-22T00:00:00+00:00'   # as strings
                                                             # 5.5 hours EARLIER as instants
```

A mandate-expiry check written on string comparison passes an expired mandate. `Mandate.active_at` was written exactly that way, and `Timestamp` was `min_length=20`, which accepted any offset.

**Chosen.** `custodian.clock` defines one spelling — UTC, second precision, `+00:00` — enforced by pattern at the schema boundary. Comparisons parse to `datetime` rather than comparing text.

**Why both halves.** The pattern gives hashing a single byte sequence per instant. Parsing gives comparison an answer that stays right even if a format slip gets past the pattern. Either alone leaves one of the two failure modes open.

**Related.** Naive datetimes are refused by `format_utc` rather than assumed to be UTC — assuming is how a five-and-a-half-hour error gets in.

---

## ADR-015 — `decide()` takes one bundled input

**Date** 2026-08-21 · **Area** gate · **Status** Accepted · **Refines ADR-010**

**Chosen.** `decide(DecisionInput) -> Decision`, where `DecisionInput` carries request id, `evaluated_at`, intent, cart, snapshot, mandate, recorded semantic verdicts and thresholds.

**Why.** Replay becomes loading one object and calling one function, with no chance of reconstructing five inputs correctly and the sixth from somewhere else. The purity boundary becomes visible — if it is not on this object, `decide()` cannot use it, and that explicitly includes the clock. And the model's position becomes structural rather than rhetorical: recorded verdicts sit in the input list beside the catalog and the mandate, so `decide()` has no client to call even if someone wanted it to.

---

## ADR-016 — Reason codes are a closed set; explanation is rendered, never authored

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Chosen.** 48 codes in a `StrEnum`, each with one line of merchant-facing text. `DimensionResult.reason_text` renders from codes. A dimension with no reason code fails validation.

**Why.** "Why did Custodian hold this order?" must be answerable without calling a model again. A free-text explanation written by an LLM is not evidence — it is a second, unverifiable model output sitting where the audit trail should be. Rendering from codes also means the eval harness can assert on *which* reason fired, not merely that something did.

**Rejected.** A `reason_text` field the gate fills in prose. It reads better and proves less.

---

## ADR-017 — An approval carrying a blocking violation is unconstructable

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Chosen.** `Decision` validates that `outcome == APPROVE` cannot coexist with any reason code in `reasons.BLOCKING`. Sixteen codes are blocking — over-mandate, over-budget, price mismatch, out-of-scope merchant, and the rest.

**Why.** "If cart total > mandate limit, cannot approve" is the property test the invariant list calls for. Enforced in the type it is stronger than a test: no downstream bug, refactor or future code path can produce that object at all. The test then verifies the guard exists rather than sampling the space of ways to violate it.

**Trade-off.** Business logic in a schema, which is normally worth avoiding. Justified here because it is the one invariant where being wrong means money moving against a violated constraint.

---

## ADR-018 — The payment interface has the provider's shape, not ours

**Date** 2026-08-21 · **Area** payments · **Status** Accepted · **Supersedes part of ADR-008**

**Problem.** ADR-008 put the provider behind a Protocol so that signup latency could not block the build. It worked — but the Protocol was designed before any live call had been made, and it was wrong.

**Context.** Established against live test-mode credentials: Razorpay is `order → (human pays) → authorized payment → capture(payment_id, amount)`. There is no call that turns an order into a payment. The original `capture(order)` described a provider that does not exist, and `FakeGateway` implemented it faithfully, so the whole contract suite was green against an imagined API.

**Chosen.** `create_order` → `payment_for(order) -> PaymentRef | None` → `capture(payment)`, with `FakeGateway.simulate_payer` standing in for the human step.

**Why the asymmetry is marked rather than removed.** Five contract tests cannot run against Razorpay, because completing a payment needs a person on a hosted page. They skip with a stated reason. The alternative — inventing a live path so the suite looks symmetrical — would restore exactly the false confidence that hid this bug through four phases of work.

**Related decision — Orders, not Payment Links.** Links yield a payable URL from a server call alone, which is attractive for a headless demo. Measured: six order creations in a burst succeed; the fourth payment-link creation returns "Too many requests". Using links per order would make a provider rate limit a property of the system, so orders are the primitive and a link is minted only when someone actually needs to pay.

**Security implication.** The order is created for the gate's re-derived total, never for the agent's asserted one. Demonstrated end to end on day 5: an agent asserting ₹99 for a ₹199 item produced a ₹896 order, not ₹696.

---

## ADR-019 — Refuse a live Razorpay key at construction

**Date** 2026-08-21 · **Area** payments, security · **Status** Accepted

**Chosen.** `RazorpayGateway.__post_init__` raises unless the key id begins `rzp_test_`.

**Why.** The thresholds are `v0-untuned` and the gate is not finished. A live key reaching this code would move real money on a decision the project itself does not yet claim is calibrated. The failure mode is a copied `.env` or a mis-set CI variable — neither of which announces itself — and refusing at construction is cheaper than trusting configuration to be right.

**Trade-off.** Anyone taking this to production must delete a line, which is the intended amount of friction.

---

## ADR-020 — A failed dimension caps the outcome, whatever the average says

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Problem.** Alignment is a weighted aggregate across eight dimensions. An aggregate can carry a failure past a threshold: an unrequested ₹1,450 wok scored 32% on scope creep and the order still reached 90.8% overall (BROKE.md 007).

**Options.** (1) Re-tune weights until failures dominate. (2) Maintain a list of blocking reason codes. (3) A structural rule on dimension status.

**Chosen.** (3), on top of (2). Any dimension with status `FAIL` or `UNCERTAIN` caps the outcome at `HOLD`; blocking codes still reject outright.

**Why.** Weights decide how much a dimension contributes to a score. They should not decide whether a failure counts — that is a separate question, and conflating them means every future weight change silently re-litigates which violations can be ignored. (2) alone depends on someone remembering to register each new code; (3) covers dimensions that do not exist yet.

**Trade-off.** The aggregate score no longer determines the outcome by itself, which makes the threshold sweep a sweep over *approvals among clean carts* rather than over all carts. That is the more honest curve anyway: the interesting question is how often a legitimate order gets held, not how often a violation can be averaged away.

---

## ADR-021 — Substitution tables are an input, not a lookup

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Problem.** `decide()` must be pure, but substitution scoring depends on the hand-authored compatibility tables, which live on disk.

**Chosen.** `SubstitutionTables` — an immutable value object extracted from the lexicon and passed to `decide()` alongside the `DecisionInput`.

**Why.** Reading a file inside `decide()` would make the decision depend on the filesystem's state at call time, and replaying it a week later would silently use a newer lexicon. As an explicit argument, the tables are visibly part of what produced the decision, and `snapshot.lexicon_version` records which version to reconstruct on replay.

**Rejected.** Embedding the table values into `DecisionInput` itself. It preserves the one-object-one-call shape, but copies the whole compatibility matrix into every ledger entry to record a fact one version string already captures.

---

## ADR-022 — Outcome-level reasons are separate from dimension reasons

**Date** 2026-08-21 · **Area** gate · **Status** Accepted

**Context.** Found by a schema invariant: a cart can pass every dimension and still fail to clear the approve threshold, or clear it with too little confidence. `Decision` refused to build, because it requires a refusal to say why and every dimension was passing.

**Chosen.** `Decision.disposition_codes` — reasons attributable to the outcome rather than to any dimension. `ALIGNMENT_BELOW_APPROVE_THRESHOLD`, `CONFIDENCE_BELOW_THRESHOLD`, `HARD_CONSTRAINT_VIOLATED`.

**Why.** "Everything checked out individually, and not by enough overall" is a real and actionable answer. Forcing it into a dimension would attribute an aggregate property to whichever axis happened to score lowest, which is a fabricated explanation.

---

## ADR-023 — Re-confirmation records authority; it does not rewrite the decision

**Date** 2026-08-21 · **Area** gate, ledger · **Status** Accepted

**Problem.** A held order that a human approves has to become settleable. The obvious implementation is to change the decision to `APPROVE`.

**Chosen.** The decision is immutable. `RECONFIRM_GRANTED` is a separate ledger event naming the actor, and `settlement_authority()` reads the pair.

**Why.** "Custodian held this order and a human overrode it at 14:32" is the truthful entry. Rewriting the outcome to `APPROVE` erases the fact that anyone had to be asked — which is exactly the fact a dispute turns on, and exactly the number the false-hold rate is measured from. An audit trail that loses the difference between "passed" and "was waved through" is not an audit trail.

**Trade-off.** Two places to look instead of one. `settlement_authority()` is the single reader, so no caller has to know the rule.

---

## ADR-024 — A rejection cannot be re-confirmed

**Date** 2026-08-21 · **Area** gate, security · **Status** Accepted

**Chosen.** `reconfirm()` raises on a request whose decision was `REJECT`. Only `HOLD` can be confirmed past.

**Why.** The three-way gate means something only if the outcomes differ in kind. `HOLD` says "I am not sure, and you are the authority" — a human answering that is the design working. `REJECT` says "a hard constraint failed": the price did not match the catalog, the mandate is spent, the merchant is not authorised. A constraint a human can wave through is advisory, and the project's central claim is that policy enforcement lives in infrastructure rather than in anyone's discretion.

**What this costs.** A genuine false rejection cannot be rescued in-flight; it needs a corrected cart, which produces a new decision and a new ledger entry. That is the right shape — the fix leaves a record of what was wrong the first time.

---

## ADR-025 — Evidence is content-addressed and stored beside the chain

**Date** 2026-08-21 · **Area** ledger · **Status** Accepted

**Problem.** A replayable decision must name every input it used. Writing the catalog snapshot into each ledger row copies seventy items per decision and makes the chain unreadable.

**Chosen.** An `artifacts` table keyed by content hash. Decision inputs lift the snapshot out by `$ref`, so one ingest serves a whole corpus run.

**Why.** Content addressing gives immutability for free — the key *is* the hash of the body, so an altered artifact stops answering to the name a decision recorded. There is no update path because there is nothing an update could mean.

**Detail worth recording.** `put_snapshot` supplies the digest explicitly rather than hashing the stored body, because a snapshot's digest deliberately excludes `snapshot_id` — that id is derived from the digest, and including it would be self-referential. Hashing the body instead produced a key that did not match the one decisions reference, which surfaced immediately as an unresolvable `$ref`.

---

## ADR-026 — The payment amount is verified again at capture

**Date** 2026-08-21 · **Area** payments, security · **Status** Accepted

**Problem.** Every check in the gate asks whether the *cart* was right. None of them asks whether the *payment in front of us* is the one that cart authorised. Between opening an order and capturing it, three things can differ: the authority may have lapsed, the payer may have committed a different amount, and the payment may not correspond to this decision at all.

**Chosen.** `Custodian.capture` re-reads `settlement_authority`, compares `payment.amount_paise` against the approved figure, and refuses on any mismatch — recording the refusal as `PAYMENT_FAILED` with both amounts.

**Why.** This is the last point at which money is still reversible, and it is a different question from everything upstream. A capture that quietly settled a mismatched amount would undo the whole verification chain at its final step, which is the answer to "what happens if payment succeeds but verification was wrong?"

**Why the refusal is recorded rather than raised and forgotten.** A mismatch is a fact about what happened. An exception that leaves no trace turns an incident into a gap in the ledger.

**Trade-off.** A legitimate partial payment cannot settle. That is intended: partial payment is a merchant policy decision, not something a verification layer should improvise.

---

## ADR-027 — A reviewed label names who reviewed it

**Date** 2026-08-21 · **Area** evaluation, integrity · **Status** Accepted

**Context.** While testing the review tool I applied three labels of my own invention to see the round-trip work. `merge_reviews` did its job and preserved them, and the corpus then carried three cases marked `HUMAN` whose calls I had made — including one that deliberately disagreed with the draft. Removed immediately, but the corpus had briefly contained exactly the circularity the whole label-provenance design exists to prevent.

**Chosen.** `Case.reviewed_by`, required whenever `label_source is HUMAN`. The schema refuses to construct an unattributed human label, and `review.py` requires `--as NAME` before it will write one.

**Why.** `PROPOSED` versus `HUMAN` records *whether* a judgment was made. It does not record *whose*, and without that a relabelled draft and a real review are indistinguishable in the file. The guard that mattered was one I had built and then walked around by accident.

**Why this is worth an ADR rather than a quiet fix.** The failure mode is not carelessness with a field; it is that the person most likely to fabricate a label is whoever is closest to wanting the number to look good. Attribution is cheap and it makes the fabrication visible to a reviewer who does not know the history.

---

## ADR-028 — A same-base substitution cannot reject, and arguably should

**Date** 2026-08-21 · **Area** gate · **Status** Open — recorded, not resolved

**Found by.** Working the benign-divergence labels case by case. `mustard seeds → mustard oil` is the same base and an entirely different ingredient: seeds pop in hot oil for a tadka, and oil does not. `whole almonds → almond milk` is the same shape of failure. Neither can reject.

**Why not.** `SUBST_BASE_UNRELATED` is blocking, so an *identity* change with no recorded relationship rejects. Form scores have no equivalent floor — an unlisted or low-scoring form pair escalates or lowers the dimension, and a failed dimension caps the outcome at `HOLD`. So a base match plus a catastrophic form mismatch is, at worst, a hold.

**Why it is being recorded rather than fixed.** The fix is not obvious. A `form_incompatible` floor needs a threshold, and the threshold needs corpus evidence to set — which needs labels that are not a model's. Adding a blocking form code now would be tuning against my own judgment, which is the exact circularity the label-provenance design exists to prevent. Two cases is also not enough evidence to design a mechanism from.

**What would settle it.** A human review of `benign-007` and `benign-014`. If both come back `REJECT`, the floor is warranted and the corpus says where to put it. If both come back `HOLD`, the current behaviour is right and this ADR closes as "considered, rejected".

**Related.** ADR-020 established that weights decide how much a dimension contributes and not whether a failure counts. This is the same question one level down: whether a *form* mismatch can be severe enough to count as a failure on its own, rather than only as a low score.

---

## ADR-029 — A model's second pass on judgment labels is recorded, not counted

**Date** 2026-08-21 · **Area** evaluation, integrity · **Status** Accepted

**Context.** Asked directly to review the 30 drafted benign-divergence labels, I did — and the result is a lesson rather than a number.

**Chosen.** `LabelSource.MACHINE_REVIEWED`, distinct from both `PROPOSED` and `HUMAN`, requiring `--machine-review` and an explicit reviewer name. `Corpus.reviewed()` excludes it; `awaiting_review()` includes it. No headline figure moves.

**Why not simply mark them `HUMAN`.** That would be fabricating provenance, and BROKE.md 010 is the record of me doing it accidentally once already.

**Why not refuse.** A concern raised and reaffirmed is the requester's decision. The second pass produced real work product: per-case reasoning a human can check in minutes rather than hours, one case flagged as genuinely low-confidence on allergen grounds, and the design gap in ADR-028.

**What it demonstrated, which is the part worth keeping.** Agreement rose from 86.67% to 100% — and every label I changed moved *toward* the gate's existing behaviour, reached by reasoning about what `REJECT` means *in this system* rather than about cooking. The conclusions are independently defensible; the route to them was contaminated. **The lower number was the more informative one.** The harness now warns when agreement on machine-reviewed labels exceeds 95%, because near-total agreement between a model's labels and a model-built gate measures consistency, not correctness.

---

## ADR-030 — A second scorer, to make swappability structural

**Date** 2026-08-30 · **Area** gate · **Status** Accepted

**Problem.** The README says "the model may propose; the runtime decides." That is a claim about architecture, and a reader has to take it on trust as long as exactly one model implementation exists.

**Chosen.** `GroqScorer` beside `ClaudeScorer`, both satisfying `SemanticScorer`, both graded by one contract suite in `tests/contract/test_semantic_scorer.py`.

**Why this and not a cheaper model on the same provider.** A second *provider* is what tests the abstraction. Two Anthropic models share a wire format, a response shape and an error taxonomy — swapping them proves the model id is a parameter, which nobody doubted. Groq's system prompt is a message rather than a parameter, its structured output is `response_format.json_schema` rather than `output_config.format`, its text arrives at `choices[0].message.content` rather than from a content-block list, and its errors are a different class hierarchy. Everything the Protocol has to absorb, it now absorbs.

**The test that carries the argument.** `test_the_gate_reaches_the_same_decision_whichever_scored_it` runs one substitution through both providers and asserts the resulting `Decision` is **byte-identical**. It can be, because the model id lives on the verdict rather than on the decision — so the answer is recorded and attributable, and what the gate concluded from it does not depend on who answered.

**A deliberate consequence.** `prompt_digest` does not include the model. The same question asked of two providers produces the same digest, which is what allows a ledger to show one substitution answered two ways. Provenance is not lost: `SemanticVerdict.model` records who answered.

**Refused: non-strict models.** Groq honours `strict: true` on a short list. Off that list the schema degrades from enforcement to suggestion, so the constructor raises and names the models that would work. An unenforced schema turns "the output is constrained" into a hope, and the whole reason a model is allowed near this decision is that its output shape is guaranteed.

**Temperature is zero.** A verdict that changes on re-ask is one the ledger cannot stand behind.

**Cost note.** Groq's free tier is ample for this — 24 escalations across the whole corpus. It is not the reason for the decision. If it were only about cost, the right answer would be to spend the ₹30 and keep one implementation.
