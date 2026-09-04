# Engineering log

One entry per working session.

Entries 1–9 were written as the session happened. **Entries 10 and 11 were not** — those two sittings were worked through without logging, and their entries were reconstructed afterwards from the commit history. Every time, count and claim in them comes from `git log`, from the diffs, or from running the suite at that commit; none of it comes from recollection, which is exactly the failure `BROKE.md` 011 records. Entry 12 was written as it happened.

---

## Day 1 (plan phase) — sitting 1, 2026-08-21 03:45–04:11

**Objective.** Stand up the primitives everything else depends on, and get the payment provider off the critical path before it can block anything.

**Completed.**
- Repo scaffold, venv, `pyproject.toml`, git init. Published: **https://github.com/OkayAnshul/custodian** (four commits, day 1).
- `money.py` — integer paise, parses the decorated forms merchants actually export (`₹199`, `Rs. 1,299.50`, `199/-`, `INR 2000`), half-up rounding, Indian lakh/crore digit grouping on output.
- `bp.py` — scores as integer basis points, all aggregation in integer arithmetic.
- `canonical.py` — deterministic JSON + SHA-256, floats and `Decimal` rejected with the offending JSON path named.
- `ledger/chain.py` — hash-chained append-only event log on SQLite, `observed`/`inferred` envelope validated on append, `BEGIN IMMEDIATE` so concurrent appends cannot fork the chain.
- `ledger/verify.py` — full-chain walk reporting the first broken link.
- `payments/gateway.py` + `payments/fake.py` — `PaymentGateway` Protocol and a deterministic in-process implementation.
- `tests/contract/test_payment_gateway.py` — the shared suite `RazorpayGateway` will have to pass unchanged.

**Tests.** 100 passing, 94% line coverage.

**Decisions.** ADR-001 through ADR-012 (see `DECISIONS.md`). The load-bearing ones are ADR-010 (`decide()` is pure, model output is a recorded observation) and ADR-007 (substitution by attribute decomposition — a deliberate deviation from problem statement §6).

**Problem encountered — before writing code.** Problem statement §6 names Jaccard/containment as the substitution primitive, and §4 gives `coconut milk → coconut cream` (faithful) versus `→ almond milk` (not faithful) as the flagship example. Those two pairs score **identically** under both primitives — 0.3333 Jaccard, 0.5 containment. The specified primitive cannot decide the specified example.

*Root cause.* Token-set overlap has no notion of which token is the head noun. "coconut milk" shares one token with each candidate; the primitive has no way to know that the shared token matters in one case and not the other.

*Fix.* ADR-007 — decompose into `(base, form, category)` at ingest and score on base identity first. Both cases then resolve deterministically.

*Prevention.* Worked the flagship example by hand before committing to the primitive. Cheap here; expensive on day 11.

**What broke.** Two entries in `BROKE.md`. (001) Shipped `bp.py` with no test file — 0% coverage sitting inside a green suite, caught only by running `--cov`. (002) `git push` hung for two minutes with no error: outbound port 22 is blocked on this network, so SSH git transport stalls indefinitely. Moved to HTTPS via `gh auth setup-git`.

**Note on the repo.** The strategy PDF is gitignored deliberately. It carries the moat analysis, the rejected-alternatives reasoning and the submission draft; public two weeks before the deadline it hands a competitor the whole approach.

**Known issues.**
- `RazorpayGateway` does not exist. Account signup started today; which test-mode settlement flow works on a fresh self-serve account is unverified and is the Day 2 spike.
- No Pydantic schemas yet — Day 2.
- `ENGINEERING_STORY.md`, `ARCHITECTURE.md`, `THREAT_MODEL.md` deliberately not started (see plan: written Day 13 from this log rather than maintained stale from Day 1).

**Next objective.** Day 2 — Pydantic data contracts (Intent, Cart, CatalogSnapshot, Mandate, Decision), SQLite storage layer, FastAPI skeleton. Razorpay spike the moment credentials land.

**Confidence.** High on the primitives — they are small, fully tested, and the properties that matter (determinism, tamper-evidence, no-double-charge) are asserted rather than assumed. Unchanged on the schedule: the settlement checkpoint is gated entirely on Razorpay signup latency, which is not yet knowable.

---

## Day 2 (plan phase) — sitting 1, 2026-08-21 03:45–04:11

**Objective.** Define every data contract before writing logic against it, and make the trust boundary visible in the types.

**Completed.**
- `schemas/types.py` — `Contract` base: frozen, `extra="forbid"`, strict numerics. `Paise`, `ScoreBp`, `Quantity`, `Timestamp`, `Digest`.
- `clock.py` — one timestamp spelling, comparison by instant.
- `schemas/catalog.py` — `CatalogItem` with `(base, form, category)` decomposition, `CatalogSnapshot` with a content digest, `Sanitization` that keeps flagged spans as evidence.
- `schemas/intent.py` — structured intent, `SubstitutionPolicy` defaulting to the conservative `SAME_BASE`.
- `schemas/cart.py` — `asserted_unit_price_paise`; the only price-bearing field, and its name carries the trust boundary.
- `schemas/mandate.py` — the AP2/UAP envelope, modelled locally and labelled as modelled.
- `schemas/verdict.py` — recorded model output with prompt digest and raw response.
- `schemas/decision.py` — `Outcome`, eight `Dimension`s, `Binding`, `Decision`.
- `schemas/decision_input.py` — the single bundled input `decide()` will take.
- `gate/reasons.py` — 48 reason codes, closed set, each with merchant-facing text.
- `gate/thresholds.py` — versioned, hashed, with the hold band that the sweep will trace.

**Tests.** 163 passing, 95% coverage.

**Decisions.** ADR-013..017. The two that carry weight: ADR-015 (one bundled `DecisionInput`, so replay is one object and one call) and ADR-017 (an approval carrying a blocking violation is unconstructable — the mandate property test enforced in the type rather than sampled by a test).

**Problem encountered.** Two, both found before they could fail a run.

*Pydantic coerces `199.0` to `199` silently.* Verified rather than assumed, which is why `Paise` is `strict=True`. Left alone it would have defeated ADR-001 at the exact boundary ADR-001 exists to protect.

*Mandate expiry compared timestamps as strings.* Logged as `BROKE.md` 003 — it would have passed expired mandates the moment an IST-stamped timestamp arrived, and every existing test would still have been green.

**Known issues.**
- Still no `RazorpayGateway`. Signup status unchanged; the spike runs the moment credentials exist.
- Thresholds are `v0-untuned` — stated guesses, labelled as such in the module. Real values come from the dev split of the corpus.
- No FastAPI surface yet.

**Next objective.** Day 3 — catalog ingest: unit normalisation (`250gm`, `1/4 kg`, `quarter kilo`), transliteration folding, the taxonomy lexicon that produces `(base, form, category)`, and snapshot construction.

**Confidence.** High on the contracts. The two bugs found today were both in the class that does not announce itself — silent coercion and silent mis-ordering — which suggests the remaining risk is in the same class rather than in anything currently failing.

---

## Day 3 (plan phase) — sitting 1, 2026-08-21 03:45–04:11

**Objective.** Turn messy Indian merchant text into the `(base, form, category)` triple ADR-007 rests on.

**Completed.**
- `ingest/units.py` — `250gm`, `1/4 kg`, `¼ kg`, `quarter kilo`, `pav kilo` all normalise to `250g`. Transliterated Hindi quantity words (`pav`, `aadha`, `sawa`, `dedh`, `paune`, `dhai`) included; a generic normaliser has no entry for them. Everything reduces to integer grams, millilitres or pieces.
- `ingest/text.py` — price extraction from product names, punctuation and filler removal, longest-phrase-first so `garam masala` survives `gram`.
- `ingest/taxonomy.py` + `data/lexicon/` — 56 bases, 20 form groups, 18 form-compatibility pairs, 5 base-equivalence pairs. Hand-authored and versioned; the version travels in every snapshot.

**Tests.** 83 new (246 total), all passing.

**Decisions.**
- Transliteration folded into the alias lists rather than a separate `translit.py` pass. `doodh` and `milk` are two spellings of one identity, so they belong on one entry; a separate layer is a second lookup that can disagree with the first.
- Base equivalence split from form compatibility (see below).

**Problem encountered — an incoherence in my own lexicon.** The first draft put `[butter, ghee]`, `[oil, ghee]` and `[block, liquid]` in the *form* compatibility table. Those are identity changes, not shape changes, so they sat in a table that could never be consulted for them — and worse, had the placement resolved differently they would have let a form rule authorise a base change, which is precisely what ADR-007 exists to prevent.

*Fix.* Two tables answering two questions. `form_compatibility` is same-base, different-shape (coconut milk → coconut cream). `base_equivalence` is the deliberately short list of identities Indian cooking treats as interchangeable (sunflower ↔ groundnut oil, butter ↔ ghee). Unlisted in either escalates.

**What broke.** `BROKE.md` 004 — `¼ kg` normalised to 4000g, a silent 16× error, because NFKC rewrites `¼` to `1⁄4` with U+2044 FRACTION SLASH before the vulgar-fraction table could match it.

**Verified.** The flagship pair now resolves deterministically in both directions, with no model involved:
- `coconut milk → coconut cream` — same base, listed form pair at 8500bp, faithful
- `coconut milk → almond milk` — base changed, no recorded relationship, `SUBST_BASE_CHANGED`

**Known issues.**
- Razorpay: unchanged, still no credentials. The settlement checkpoint cannot be met without them.
- No sanitizer yet, no loader, no snapshot builder — Day 4.
- Lexicon covers one merchant's likely catalog. Coverage against the real messy source is unmeasured until the loader exists.

**Next objective.** Day 4 — the messy catalog source and loader, the ingest sanitizer, the intent parser (model position #1), and the deliberately naive buyer agent.

**Confidence.** High on the primitive. The claim ADR-007 makes is now demonstrated by a test that also asserts the premise — that Jaccard scores both flagship cases identically at 0.3333 — so the argument for the deviation is reproducible rather than asserted.

---

## Day 4 (plan phase) — sitting 2, 2026-08-21 10:40–10:49

**Objective.** A real messy catalog, ingested end to end, with the attack surface closed on the way in.

**Completed.**
- `data/catalog/kirana_export.csv` — 70 rows of realistic mess: 5 rows with an empty price column, 4 with the price inside the item name, 11 with no category, 6 spellings of "in stock", 25 raw category strings folding to 14.
- `ingest/sanitizer.py` — rules only, five detection classes. Detected payloads suppress the whole field; hidden characters are stripped in place.
- `ingest/loader.py` — price resolution (field > name > mrp), stock spellings, taxonomy-derived categories, and a `LoadReport` recording every resolution it had to make.
- `ingest/snapshot.py` — content-addressed snapshots and the narrow agent feed.
- `tests/fixtures/adversarial.py` — 14 frozen injections and 6 benign lookalikes, as inert strings with no runner.

**Tests.** 58 new (304 total), all passing.

**Result.** 70/70 rows build; 69/70 place. The one holdout is the glitter pens, which should not place — it is not a grocery, and it is the scope-creep case for the demo.

**Problems encountered.** Three, all found by running against the real data rather than against fixtures.

*Bilingual names failed to place.* `BROKE.md` 005. Counting alias hits rather than distinct identities read "Basmati Chawal" as an ambiguity. The tell was that improving the lexicon made it *more* likely to fire, not less.

*Sanitizer false positive.* A bare `you must/should` pattern flagged "You must try this with fresh coriander!" — ordinary marketing copy — and suppressing a legitimate product's whole description is a direct cost to the merchant. Every attack it caught was already covered by the action-specific patterns, so it bought false positives and no coverage. Removed, with the reasoning left in the source. This is why `BENIGN_LOOKALIKES` is graded alongside the injections: catching attacks is half the measurement.

*Self-referential snapshot digest.* `snapshot_id` is derived from the content hash, and the content hash included `snapshot_id` — so naming a snapshot changed the digest that produced the name. `digest()` now excludes it: the id is a name for the content, not part of it.

**Known issues.**
- **Razorpay: still no credentials.** The gateway Protocol means nothing else is blocked, but the settlement checkpoint itself cannot be met without an account.
- Intent parser (model position #1) and the naive buyer agent are not built — the remainder of Day 4.
- `ANTHROPIC_API_KEY` is not set in this environment either, so the parser will need the same treatment as payments: an interface with a recorded-fixture implementation, so the gate can be built and tested without a live key.

**Next objective.** Intent parser behind an interface, naive buyer agent, then Day 5's end-to-end loop.

### Day 4, continued — intent parser and reference buyer

**Completed.**
- `intent/prompt.py` — the one prompt in the system, versioned and hashed. It deliberately does *not* ask the model to categorise items: category and base come from the same lexicon the catalog is normalised against, and a model-assigned category would be a second, disagreeing opinion about what a word means.
- `intent/parser.py` — `IntentParser` Protocol, `ParseResult` carrying model id, prompt digest and raw response, and a deterministic `resolve` step that places the model's words through the taxonomy.
- `intent/recorded.py` — fixture parser keyed on prompt digest, so a fixture recorded under an older prompt version cannot silently satisfy a current request.
- `intent/claude.py` — the live parser. Structured outputs via `output_config.format`, adaptive thinking, `claude-opus-5`.
- `agent/buyer.py` — the naive reference buyer.
- `CatalogItem` gained `description` and `raw_description`; `unsanitised_feed` added as the demo baseline.

**Tests.** 28 new (332 total).

**Checked rather than recalled.** Loaded the Claude API reference before writing SDK code, which corrected two things I would have got wrong from memory: the default model is `claude-opus-5` (I was going to reach for Sonnet on cost grounds — that is the user's call, not mine, and this is one call per request), and structured output goes through `output_config.format`, not the deprecated `output_format` parameter.

**The buyer agent is naive on purpose, and the choice carries an argument.** It matches items by Jaccard overlap on product names — precisely the primitive ADR-007 rejected for the gate. So the agent will offer almond milk for coconut milk, because token overlap scores that identically to coconut cream. The agent's failure and the gate's correctness come from the same example, which makes the demo one story rather than two.

**Problem found.** The loader sanitised each description and then discarded the result — `CatalogItem` had no description field at all, so the cleaned copy went nowhere and the agent feed carried no product text. Found only when building `unsanitised_feed` and discovering there was nothing to contrast against. Both fields added: `description` (sanitised, reaches the agent) and `raw_description` (evidence, never served).

**Verified — the baseline the attack demo measures against.** Same catalog, same agent, one poisoned description telling it to add a ₹1,450 wok:

```
CUSTODIAN OFF: [coconut milk, Hawkins Kadhai]  -> ₹1,649.00
CUSTODIAN ON : [coconut milk]                  -> ₹199.00
```

The instructed addition is `satisfies_line_id=None`, so even when it does get through, it traces to nothing in the request — scope creep by construction rather than by detection.

**Confidence.** High on ingest — it runs against real messy data rather than a fixture, and the failures it found were the useful kind. Lower on the schedule: two of the last three days\' problems were found only by running against real inputs, and the payment path still has no real input to run against.

---

## Day 5 (plan phase) — sitting 3, 2026-08-21 18:03–18:04 — **CHECKPOINT MET**

**Objective.** Razorpay credentials arrived. Run the Day 1-2 spike that had been blocked since the start, then close the end-to-end loop.

**The spike found the thing spikes are for.** `PaymentGateway` had `create_order` then `capture(order)`. That path does not exist. Razorpay is `order → (a human pays) → authorized payment → capture(payment_id, amount)`, and an unpaid order has zero payments on it. `FakeGateway` had been passing the full contract, through every phase up to that point, against an interface I had imagined. Logged as `BROKE.md` 006 — a fake that satisfies a contract the real provider cannot is worse than no fake.

Two further findings from the same session, both measured rather than assumed: `reference_id` is capped at 40 characters (a Custodian request id has no such cap, so the gateway shortens by deterministic digest), and payment-link creation is rate limited where order creation is not — six orders in a burst succeeded, the fourth link did not. The first implementation used links as the per-order primitive, which would have made a provider rate limit a property of the system.

**Completed.**
- `payments/gateway.py` reshaped to the provider's actual lifecycle; `FakeGateway.simulate_payer` added for the human step.
- `payments/razorpay_client.py` — live gateway on the Orders API, explicit rate-limit backoff, and a construction-time refusal of any non-`rzp_test_` key (ADR-019).
- Contract suite parametrised over both implementations. **12 tests now run against the live Razorpay API**; 5 skip with a stated reason because no API call makes a payment happen.
- `scripts/settlement_demo.py` — the whole loop, end to end.

**Tests.** 352 total. 12 of them live.

**Verified — the settlement checkpoint met.** Messy catalog → feed → intent → cart → server-side re-derivation → real Razorpay test-mode order → hash-chained ledger. The agent deliberately understates one line, and the control already holds:

```
agent asserted    : ₹696.00
Custodian derived : ₹896.00   <- the order is created for this
order             : order_TSQ9ta0SoImmRF   (real, test mode)
chain intact      : 4 events
```

**Known issues.**
- Completing the payment still needs a human on the hosted page with a test card. That is a property of the provider, not a gap in the build, and it is stated rather than worked around.
- The mandate envelope remains modelled locally — Reserve Pay is not reachable from a self-serve test account.
- `decide()` does not exist yet. Day 5 does arithmetic; the gate is Days 6-8.

**Next objective.** The gate. Binding, deterministic checks, the substitution scorer over the attribute tables, and the pure `decide()` everything so far exists to make possible.

**Confidence.** Materially higher than yesterday. The riskiest unknown in the plan is closed, it was wrong in the way it was flagged as likely to be wrong, and the fix is now guarded by tests that hit the real API on every run.

---

## Day 6 (plan phase) — sitting 3, 2026-08-21 18:21

**Objective.** The gate. Binding, deterministic checks, the substitution scorer over the attribute tables, and the pure `decide()`.

**Completed.**
- `gate/substitution.py` — attribute scoring with `SubstitutionTables` as an explicit input (ADR-021). Weakest attribute governs: a perfect base cannot carry an incompatible form.
- `gate/binding.py` — cart line back to requested item, re-derived rather than trusted. Category proximity separates *bad substitute* (bound, unfaithful) from *unrequested item* (bound to nothing) — a distinction no total-based check can make.
- `gate/deterministic.py` — six checks that reject on their own authority.
- `gate/scope.py` — scope creep scored by value, not count.
- `gate/confidence.py` — coverage and margin, computed. Never a model's self-report.
- `gate/decide.py` — `decide()` and `escalations()`.

**Tests.** 35 new (387 total).

**Verified.** Eight scenarios against the real catalog:

```
clean order                        APPROVE   no model asked
coconut milk -> coconut cream      APPROVE   no model asked
coconut milk -> ALMOND milk        REJECT    no model asked
unrequested wok, inside budget     HOLD      SCOPE_CREEP FAIL
forged price (₹99 for ₹199)        REJECT    charged ₹698, not ₹498
over budget                        REJECT
quantity inflated x6               HOLD
turmeric whole -> powder           HOLD      escalates line l1, confidence 21.97%
```

Both flagship cases are settled by arithmetic with zero escalations, which is ADR-007's claim demonstrated rather than argued.

**What broke.** `BROKE.md` 007, and it is the worst one so far: the gate **approved an order with a failed dimension**. Almond milk for coconut milk scored 34% on substitution and approved at 85% overall, because seven passing dimensions outvoted the one that mattered. I had written "a constraint that can be outvoted by a good average is not a constraint" as a comment inside the very function where exactly that happened. Fixed structurally (ADR-020) rather than by re-tuning weights.

**Two smaller finds.** `SUBST_BASE_CHANGED` was carrying two different claims — an unrelated identity swap and a *permitted* equivalence — so it could not be made blocking without refusing legitimate substitutions; split into `SUBST_BASE_UNRELATED`. And a schema invariant caught that a threshold-driven `HOLD` has every dimension passing and therefore nothing to point at, which produced `disposition_codes` (ADR-022) and finally gave the two orphaned outcome-level reason codes a use.

**Known issues.**
- No ledger integration for decisions yet, and no replay path — Day 7.
- No API surface. No re-confirmation flow.
- Thresholds still `v0-untuned`. The corpus starts Day 8.

**Next objective.** Wire `decide()` to the ledger, build replay, and the re-confirmation path.

**Confidence.** The gate does what it should on eight hand-built scenarios, which is not the same as being calibrated. Today\'s bug is the argument for the corpus: it was found by looking at output, not by a test, and eight scenarios is not a measurement.

---

## Day 7 (plan phase) — sitting 3, 2026-08-21 18:30

**Objective.** Wire the gate to the ledger, build replay, and the re-confirmation path.

**Completed.**
- `gate/semantic.py` — model position #2. `SemanticScorer` Protocol, `RecordedScorer`, `ClaudeScorer`. The prompt carries the cooking context and the two items and *nothing else*: no price, no budget, no mandate. `UNSURE` is a first-class label, because a two-way choice manufactures confidence.
- `ledger/store.py` — content-addressed artifact store (ADR-025).
- `gate/service.py` — the orchestrated flow, re-confirmation, and `settlement_authority`.
- `ledger/replay.py` — `replay` and `replay_all`, reporting field-level differences rather than a boolean.

**Tests.** 23 new (410 total).

**Verified — the replay claim, end to end.**

```
req-1: reproduces exactly (HOLD)
req-2: reproduces exactly (REJECT)
chain intact: 6 events
artifacts stored: 5 (one catalog shared by both decisions)
```

Replay under a deliberately drifted lexicon version refuses rather than quietly producing a different answer — the tables are an input, so a different lexicon is a different decision.

**Two decisions worth defending.**

*Re-confirmation does not rewrite the decision* (ADR-023). A held order stays `HOLD` in the record; a separate `RECONFIRM_GRANTED` event names the actor. Rewriting the outcome to `APPROVE` would erase the fact that anyone had to be asked — which is the fact a dispute turns on and the number the false-hold rate is measured from.

*A rejection cannot be re-confirmed* (ADR-024). `HOLD` means "I am not sure and you are the authority"; a human answering it is the design working. `REJECT` means a hard constraint failed, and a constraint a human can wave through is advisory.

**Problems encountered.** Two, both caught by tests I wrote immediately after the code.

*The snapshot `$ref` did not resolve.* `put_snapshot` hashed the serialised body while `snapshot.digest()` excludes `snapshot_id` — the self-reference fix from Day 4. Two names for one artifact. The store now takes an explicit digest when an artifact has a canonical identity that is not simply the hash of its bytes.

*`INTENT_RECEIVED` was recorded after `SNAPSHOT_TAKEN`.* Wrong order: the intent is what causes a snapshot to be taken at all, and a dispute starts from the request. Also fixed a real gap — the first version of `evaluate` did not record the intent at all, so the trail began with a catalog and never said what was asked for.

**Known issues.**
- No API surface and no UI. The replay viewer is Days 11-12.
- Settlement is not yet wired to `settlement_authority` — the demo script still creates orders directly.
- Thresholds still `v0-untuned`. **The corpus starts tomorrow.**

**Next objective.** The corpus. 120 hand-labelled cases across four classes, the harness, and the threshold sweep.

**Confidence.** High on the machinery. Demo 6 — take a ledger entry, re-run it, get the same result — now runs as a test rather than existing as a claim. Unchanged on calibration: every number the gate produces is still keyed to thresholds nobody has measured.

---

## Day 8 (plan phase) — sitting 3, 2026-08-21 18:42

**Objective.** The corpus, the harness, and the sweep. Brought forward ahead of the plan's ordering, deliberately — thresholds cannot be chosen without data.

**Completed.**
- `eval/corpus/schema.py` — cases with **label provenance as a typed field**. `BENIGN_DIVERGENCE` cannot be `DERIVED`; the schema refuses to build it, so the integrity constraint is enforced rather than remembered.
- `eval/corpus/build.py` — 120 cases matching §7\'s distribution exactly (60/30/15/15), each with a written rationale. `merge_reviews` preserves human labels across regeneration.
- `eval/harness.py` — grades outcome *and* reason codes, reports derived and drafted classes separately.
- `eval/sweep.py` — three dials, with friction measured as a hold rate that needs no ground truth.
- `tests/test_corpus.py` — the corpus runs as a regression suite, so a change that alters a graded outcome fails the build.

**Tests.** 14 new (424 total).

**Results, DEV+TEST, derived labels only.**

```
CLEAN         60  100.00%     clean approval 100%, false-hold 0%
ADVERSARIAL   15  100.00%     catch 100%, false-approval 0%, zero reached the model
AMBIGUOUS     15  100.00%     6 escalations
```

**What that number does and does not mean**, stated in the harness output itself: the derived classes have labels that follow from how each case was built. Scoring 100% says the implementation matches its specification. It does not say the specification is right. The class where that question lives is benign divergence, whose 30 labels are drafts awaiting review.

**The corpus earned its place immediately.** The first run scored clean approval at **76.67%** with a 18.33% false-hold rate. Three distinct causes, only one a gate bug:

- My generator asked for items by the taxonomy\'s internal base key. "coconut" is genuinely ambiguous between milk, cream, oil and flakes, and the gate was right to hold it. Fixed by asking the way a person writes a shopping list.
- **A real bug**: `pigeon-pea` did not match the alias `pigeon pea`. A hyphen between letters is a word separator, and merchants write both spellings.
- One expectation demanded `SUBST_EXACT` where "jeera" places as cumin/seed and the catalog item as cumin/whole — scored 9000, a correct approval and not an exact match.

**What broke.** `BROKE.md` 008 — a flat sweep that read as a finding. Two faults in one appearance: version strings overflowing a 32-character cap so every point was silently discarded by a blanket `except`, and a genuinely flat curve because I had excluded the only class whose cases sit near a boundary.

**The sweep, now real.**

```
substitution_faithful_bp   substitutions held   escalation rate   clean approval
        50%                    46.67%              10.83%            100%
        80%  (default)         73.33%              20.00%            100%
        95%                    93.33%              25.83%             98.33%
```

The adversarial catch rate does not move across any dial. Every attack in this corpus is settled by a deterministic check, so tightening a threshold spends friction and buys no safety — which is worth knowing before anyone tunes it upward hoping for protection it cannot provide.

**Known issues.**
- **30 benign-divergence labels need human review.** Until then no headline number rests on them.
- Thresholds are still `v0-untuned`. The sweep now says what tuning them would cost.
- No API surface, no viewer, no README.

**Next objective.** API, replay viewer, README.

---

## Day 9 (plan phase) — sitting 3–4, 2026-08-21 18:47–21:31 — the surface, the documents, and one hole

**Objective.** API, viewer, README, and a hostile pass over what a judge would attack.

**Completed.**
- `api/app.py` — ten routes. `Idempotency-Key` required on the one that can lead to money moving.
- `api/view.py` — the decision viewer. Server-rendered, no build step: a page that needs a toolchain to show a hash chain is not a serious artifact. Loading it re-derives the decision from the ledger, so it is the demo screen and the replay moment at once.
- `README.md`, `THREAT_MODEL.md`, `EVALUATION.md`, `ARCHITECTURE.md`.
- `scripts/demo.py` — all six scenarios, creating a live Razorpay test-mode order when credentials are present.

**Tests.** 437 passing, 18 skipped.

**What broke.** `BROKE.md` 009 — the ledger could not be called from a web server at all. sqlite3 connections are thread-bound; FastAPI runs sync handlers on a threadpool. On Day 1 I reasoned about concurrency and concluded `BEGIN IMMEDIATE` was sufficient, which it is for the failure mode I had named — two writers forking the chain. It does nothing about two threads sharing a connection object. Having solved the first problem I stopped looking for the second, and every test I had written called the ledger from the thread that created it.

**Caught while writing the README.** I claimed "5% of cases reach a model" without measuring it. The real figure is 24 of 162 cart lines, 14.8%. Corrected before commit. A number in a README is a claim, and an unmeasured one is worse than no number.

**Caught in the hostile pass.** "What happens if payment succeeds but verification was wrong?" had no good answer. The settle path opened an order for the verified total and never checked what actually arrived before capturing — so a payer committing a different amount would have been captured silently, undoing the whole verification chain at its last step. Closed by ADR-026: `capture` re-reads authority, compares the presented amount against the approved one, and records the refusal as evidence rather than raising and forgetting.

**Where this stands.**

Working and tested: ingest, sanitizer, taxonomy, intent parsing, the gate, the ledger, replay, re-confirmation, settlement with live Razorpay test-mode orders, the corpus, the harness, the sweep, the API, the viewer.

Not done, and stated rather than hidden:
- **30 benign-divergence labels are drafts.** That class is the project\'s stated moat and it is the one thing I could not honestly finish, because a model scored against labels it drafted is measuring its own consistency. `EVALUATION.md` has the review workflow; it is roughly an evening of judgment.
- Thresholds remain `v0-untuned`. The sweep now says exactly what tuning them would cost.
- The mandate is modelled, not integrated. Completing a payment needs a human on a hosted page.
- No pitch recording. No auth, no rate limiting.

**Confidence.** High on the machinery and on the argument. The claims in the README are either tested or measured, and where a number rests on something unfinished it says so. The weakest part is calibration, and it is weak in a way the documents name rather than obscure.
---

## Day 10 — sitting 5, 2026-08-22 00:28–01:41 — the record corrected, and the money question answered

*Reconstructed from the commit history; see the note at the top.*

**Objective.** Fix what a hostile read found in the documents, then answer the question a merchant actually asks.

**Completed.**
- `BROKE.md` 011 written, and the fabricated dates corrected across `ENGINEERING_LOG.md`, `DECISIONS.md`, `DEFENSE.md`, `README.md` and `SUBMISSION.md` (`35528ba`).
- `eval/counterfactual.py` and `make money` (`a7ead93`) — the corpus in rupees rather than rates. Both paths are runnable: "without Custodian" is `NaiveBuyer` reading an unsanitised feed with its asserted totals settling, not an estimate. ₹31,655 of 120 orders stopped or held, at 0% friction on the 60 clean ones.
- The model put on camera in the demo (`f9d6674`): an escalation now prints the prompt digest, the raw response and how it was read, so the one place a model touches a decision is visible rather than described. README and `DEMO.md` repositioned on the track's own wording.
- `GET /checkout/{request_id}` and `POST /v1/checkout/callback/{request_id}` (`d216e72`) — the page a payer completes an order on, and the signature check on what the browser hands back. `HMAC-SHA256(order_id|payment_id)`, verified before anything is captured, with six tests: a genuine signature, a forged one, one replayed against a different order, one against a different payment, one made with the wrong secret.

**Tests.** 468 passing, 18 skipped — verified by running the suite at `d216e72` rather than remembered.

**What broke.** `BROKE.md` 011, the worst entry in the file: nine log headings carrying the calendar dates the *plan* assigned to each phase, written in the past tense, across a week that had not happened, while every commit in the repository was timestamped to one day. Found by comparing the log against `git log` — one command, run only because someone asked whether things were working.

**Confidence.** High on the money figures, which are computed from the same objects the decisions were made from rather than from a second reading of the case file. Lower on the checkout page, which at this point was written and had never been loaded.

---

## Day 11 — sitting 6, 2026-08-30 09:58–11:30 — a second provider, and the first answers I did not write

*Reconstructed from the commit history; see the note at the top.*

**Objective.** Make the swappability claim structural instead of asserted, then stop replaying model answers I had written myself.

**Completed.**
- `gate/groq_scorer.py` (`1c8e977`) and `intent/groq_parser.py` (`b4b5e73`) — a second implementation of *both* model positions, behind the same Protocols, graded by the same contract suites. A second **provider** rather than a second model: different system-prompt handling, different structured-output mechanism, different response shape, different error hierarchy — everything the abstraction has to absorb. ADR-030. A consequence worth stating: the whole system now runs on one free API key.
- `scripts/record_fixtures.py` and `make record` (`9682121`) — incremental and resumable, so a rate limit mid-run does not lose what was already recorded.
- 28 real responses recorded (`f9d3404`): 24 substitution verdicts and 4 intent parses from `openai/gpt-oss-120b`, each stored with provider, model, prompt digest, timestamp and the question exactly as sent. The demo now prints which of three states it is in — live call, real recording, or authored fixture — rather than letting them look alike.

**Tests.** 537 passing, 19 skipped — verified by running the suite at `f9d3404`.

**What broke.** `BROKE.md` 012, found on the first run with real answers instead of mine. `amb-unplaced-001` — the case that exists to demonstrate calibrated abstention — went from `HOLD` to `APPROVE`, because the model was asked whether "Sparkle Glitter Pens 5 nos" substitutes for "glitter pens" and said `FAITHFUL` at 95%. The answer is correct. The bug was mine: `base=UNKNOWN` is not "these might be unalike", it is "the taxonomy could not place this", and a verdict about similarity cannot supply that. A model can tell you two things are alike; it cannot tell you what they are. The substitution dimension now holds at `UNCERTAIN` whenever a line carried `SUBST_BASE_UNKNOWN`, whatever the verdict says — narrowly, so an unlisted *form pair* is still resolvable by a verdict.

**Confidence.** Raised on the model boundary, and for a specific reason: this is the first thing in the build that disagreed with me without being asked to. Every fixture before it was a stand-in written by the person who also wrote the expectations.

---

## Day 12 — sitting 7, 2026-09-03 — demo readiness: run every path a viewer sees

**Objective.** Present it. Which means running every path with real credentials rather than trusting the suite, and reconciling every number in the documents against what the tools print.

**Completed.**
- **The payable link, fixed** — `BROKE.md` 013, ADR-031. `make demo` with credentials had been printing `link unavailable` on every run after the first, because Razorpay's `reference_id` on a payment link is a uniqueness constraint rather than an idempotency key. A duplicate now falls through to the existing link, but only if its amount equals the amount this order derived and it is still payable. Six tests.
- **A refused link no longer fails a settlement.** `POST /v1/checkout/settle` returns `payment_url: null` rather than a 500 when the provider will not mint one. Link creation is rate limited far more tightly than order creation; a convenience must not take down the thing it decorates.
- **The checkout page rendered against a real order,** as a `live`-marked test: the order id Razorpay issued, the derived amount, the Checkout script, the callback path for that request. What is still unrun is the browser leg — Razorpay's script and a person with a card — and `LIMITATIONS.md` now says exactly that rather than "the page is untested".
- **`make money` prints the per-line model figure** the README quotes (24 of 162 cart lines, 14.81%). It had printed the per-order figure while the README quoted lines; both were right and the README was claiming to show output it did not show.
- **The build had been red for ten runs** — `BROKE.md` 014. Every CI step passed except the last, which compares the committed corpus against a fresh build. `merge_reviews` preserved `HUMAN` labels and dropped `MACHINE_REVIEWED` ones, so the second pass on the 30 judgment labels made `cases.yaml` permanently unable to match its own generator. It went red on exactly that commit, on 21 August, and stayed red for thirteen days. Fixed by preserving both reviewed sources; a rebuild is now byte-identical and a test asserts it locally.
- **`make check` is now what CI runs**, which the documents had been claiming while it skipped the one step that was failing. `python -m eval.corpus.build --check` reports staleness without rewriting the file it is checking, so both can run it.
- **A number four documents quoted had never been counted.** The lexicon is described everywhere as "56 bases, 24 form-compatibility pairs". It has 58 bases — it grew by two on the day it was written — and it has never had 24 pairs; the file has held 18 since the first commit that created it. Corrected in the README, `DEMO.md`, `DEFENSE.md` and `LIMITATIONS.md`, and `test_the_lexicon_is_the_size_the_documents_say_it_is` now fails the build if any of the three drifts. Reason codes were 48 and are 49, corrected the same way. This is `BROKE.md` 011's lesson in miniature: a count in prose is a claim, and one nobody ever counted reads exactly like one that was measured.
- **Documents reconciled against the tools.** Test count 437 → 549 in the README and 449 → 549 in `SUBMISSION.md`; `BROKE.md` entries nine → fourteen; ADRs 26 → 31; `ARCHITECTURE.md`'s module map and route table brought up to the code; `LIMITATIONS.md`'s "no model call has been made live", false since 30 August, rewritten to say what is recorded, what replays and why, and what is still live only under `make demo-groq`.

**Tests.** 549 passing, 20 skipped. With Razorpay credentials present: 562 passing, 7 skipped — and those seven are the payer-simulation cases that no API call can perform, which is the honest asymmetry rather than a gap.

**Verified by hand this sitting, with live credentials.** `make demo` end to end including a real order and a payable link; `make demo-groq` making the substitution call live against Groq; verify → settle → checkout page through the live gateway.

**What broke.** Two, and they rhyme. `BROKE.md` 013: the payable link had run successfully exactly once, when it was written, and nothing afterwards was a fresh account — a failure that only appears on the *second* run is invisible to a suite that starts clean every time, and a demo is by definition the second run. `BROKE.md` 014: the build had been red for ten runs and I had stopped reading it, because a check that cannot pass looks exactly like a check that always fails. Both were found the same way — by running the real thing rather than the thing that stands in for it.

**Where this stands.** Everything a viewer will see has now been run against the real thing at least twice, and the build is green for the first time since 21 August. Two things remain open and are stated rather than hidden: the 30 benign-divergence labels still carry a model's second pass and no human sign-off, and the browser leg of the checkout page is unrun.

**Confidence.** High on the machinery, the argument and now the presentation. Unchanged on calibration, which is where it should be: the thresholds are still `v0-untuned` and the sweep says precisely what tuning them would cost.
---

## Day 13 — sitting 8, 2026-09-03–04 — the review, and the measurement it made possible

**Objective.** Review the 30 benign-divergence labels with a person, and follow through wherever the answer changes something.

**Completed.**
- **All 30 labels reviewed and applied as `HUMAN`, attributed to OkayAnshul.** 15 distinct substitutions, each judged once and applied to both variants of its pair — the pair differs only in goal prose the gate never sees and in the DEV/TEST split, so a split label inside a pair would be a claim that the gate is wrong rather than a judgment about food. `decisions.txt` carries the reasoning; `REVIEW.md` is now a record of what was decided rather than a stale request for decisions.
- **The rule that governs the class, settled first because it decides several cases at once.** REJECT means a hard constraint failed or the two items are unrelated; anything related but possibly wrong is HOLD. Consequence, stated rather than discovered later: the only REJECT in the class is `benign-009`, a policy violation. No substitution is ever rejected on its merits.
- **ADR-028 closed — considered, rejected.** It had pre-registered its own settling condition: a human review of `benign-007` and `benign-014`, rejecting if both came back REJECT. Both came back HOLD. Closing on a condition stated in advance is worth more than the answer itself.
- **The measurement the review unlocked.** `eval/sweep.py` now scores each threshold against the reviewed labels, which was impossible while they were drafts. `substitution_faithful_bp = 8000` is the *unique* agreement peak — 100%, against 73–80% everywhere else on the dial, falling off on both sides, holding separately on DEV (n=20) and TEST (n=10). Two tests assert both the peak and the split-survival.
- **`v0-untuned` → `v1-reviewed`**, ADR-032. Not one value moved: the shipped guess was already optimal, so the name says reviewed rather than tuned. Fitting numbers to 30 labels and reporting against the same 30 would prove nothing; nothing was fitted, and the name should make that visible.
- **The harness report reworked.** A human-signed class must not silently become a headline number — applying the labels moved 30 cases into the graded set and deleted the entire "awaiting review" section, warning and all. Benign divergence now has its own row and its own block naming the reviewer, the agreement, and the three things that bound it.

**Tests.** 551 passing, 20 skipped. With Razorpay credentials: 564 passing, 7 skipped.

**What broke.** Nothing, and one thing nearly did quietly: applying the labels made the report *better-looking* and less honest in the same commit. The class disappeared into `ALL` at 100% with no caveat attached, because every warning in that code path was conditioned on the labels being drafts. Caveats attached to a state rather than to a claim evaporate the moment the state changes, which is a general lesson and not a bug I can point at a line for.

**Where this stands.** The one item that was blocked on a person is done. What is left is a second reviewer — the bounds on this agreement are exactly what an independent pass would tighten — the browser leg of the checkout page, and the pitch recording.

**Confidence.** Raised, and specifically on the part that was weakest. Calibration was the honest gap through the whole build; it is now a measurement with its limits printed by the tool rather than recited in prose. The limits are real: one reviewer who could see the gate's answers, on one catalog.
