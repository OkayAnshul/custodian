# Engineering log

One entry per working session. Written as the session happens, not reconstructed afterwards.

---

## Day 1 — 2026-08-21

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

**Confidence.** High on the primitives — they are small, fully tested, and the properties that matter (determinism, tamper-evidence, no-double-charge) are asserted rather than assumed. Unchanged on the schedule: Day 5 is gated entirely on Razorpay signup latency, which is not yet knowable.

---

## Day 2 — 2026-08-22

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

## Day 3 — 2026-08-23

**Objective.** Turn messy Indian merchant text into the `(base, form, category)` triple ADR-007 rests on.

**Completed.**
- `ingest/units.py` — `250gm`, `1/4 kg`, `¼ kg`, `quarter kilo`, `pav kilo` all normalise to `250g`. Transliterated Hindi quantity words (`pav`, `aadha`, `sawa`, `dedh`, `paune`, `dhai`) included; a generic normaliser has no entry for them. Everything reduces to integer grams, millilitres or pieces.
- `ingest/text.py` — price extraction from product names, punctuation and filler removal, longest-phrase-first so `garam masala` survives `gram`.
- `ingest/taxonomy.py` + `data/lexicon/` — 56 bases, 20 form groups, 24 form-compatibility pairs, 5 base-equivalence pairs. Hand-authored and versioned; the version travels in every snapshot.

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
- Razorpay: unchanged, still no credentials. Day 5 is Aug 25.
- No sanitizer yet, no loader, no snapshot builder — Day 4.
- Lexicon covers one merchant's likely catalog. Coverage against the real messy source is unmeasured until the loader exists.

**Next objective.** Day 4 — the messy catalog source and loader, the ingest sanitizer, the intent parser (model position #1), and the deliberately naive buyer agent.

**Confidence.** High on the primitive. The claim ADR-007 makes is now demonstrated by a test that also asserts the premise — that Jaccard scores both flagship cases identically at 0.3333 — so the argument for the deviation is reproducible rather than asserted.

---

## Day 4 — 2026-08-24

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
- **Razorpay: still no credentials, and Day 5 is tomorrow.** The gateway Protocol means nothing else is blocked, but the checkpoint itself cannot be met without an account.
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

## Day 5 — 2026-08-25 — **CHECKPOINT MET**

**Objective.** Razorpay credentials arrived. Run the Day 1-2 spike that had been blocked since the start, then close the end-to-end loop.

**The spike found the thing spikes are for.** `PaymentGateway` had `create_order` then `capture(order)`. That path does not exist. Razorpay is `order → (a human pays) → authorized payment → capture(payment_id, amount)`, and an unpaid order has zero payments on it. `FakeGateway` had been passing the full contract for four days against an interface I had imagined. Logged as `BROKE.md` 006 — a fake that satisfies a contract the real provider cannot is worse than no fake.

Two further findings from the same session, both measured rather than assumed: `reference_id` is capped at 40 characters (a Custodian request id has no such cap, so the gateway shortens by deterministic digest), and payment-link creation is rate limited where order creation is not — six orders in a burst succeeded, the fourth link did not. The first implementation used links as the per-order primitive, which would have made a provider rate limit a property of the system.

**Completed.**
- `payments/gateway.py` reshaped to the provider's actual lifecycle; `FakeGateway.simulate_payer` added for the human step.
- `payments/razorpay_client.py` — live gateway on the Orders API, explicit rate-limit backoff, and a construction-time refusal of any non-`rzp_test_` key (ADR-019).
- Contract suite parametrised over both implementations. **12 tests now run against the live Razorpay API**; 5 skip with a stated reason because no API call makes a payment happen.
- `scripts/settlement_demo.py` — the whole loop, end to end.

**Tests.** 352 total. 12 of them live.

**Verified — the Day 5 checkpoint, four days early.** Messy catalog → feed → intent → cart → server-side re-derivation → real Razorpay test-mode order → hash-chained ledger. The agent deliberately understates one line, and the control already holds:

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

## Day 6 — 2026-08-26

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
