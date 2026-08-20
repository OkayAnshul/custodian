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
