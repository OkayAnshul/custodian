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
