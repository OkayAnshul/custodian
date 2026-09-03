# Architecture

The README covers the thesis and the results. This is the map: modules, contracts, and the one invariant everything else was shaped to preserve.

## The load-bearing invariant

```python
def decide(inp: DecisionInput, *, tables: SubstitutionTables) -> Decision:
    """No clock. No network. No randomness. No dict-order dependence."""
```

Given the same input and tables, the same bytes, every time. Everything below exists to make that true and to keep it true.

It resolves what would otherwise be a contradiction — a decision that a model participates in, and that replays without one. The model runs **upstream**; its verdict is written to the ledger as an *observation*, with the same standing as a catalog price. Replay reads the recorded verdict and re-runs `decide()`. Tested with the model client mocked to raise if called.

Two consequences that reach everywhere:

- **Money is integer paise.** Floats have no canonical byte form, so a float amount in a ledger payload makes the chain non-reproducible across platforms.
- **Scores are integer basis points.** Same reason. A replay assertion written as `abs(a - b) < 1e-9` is not the same claim as "the same decision".

The serialiser enforces both: `canonical_bytes` refuses any float or `Decimal` and names the offending JSON path.

## Modules

```
src/custodian/
  money.py            int paise; parses ₹199, Rs. 1,299.50, 199/-; lakh/crore output
  bp.py               integer basis points; all aggregation in integer arithmetic
  canonical.py        deterministic JSON + SHA-256; refuses floats
  clock.py            one timestamp spelling; comparison by instant, not by text

  schemas/            the contracts that cross trust boundaries
    types.py          Contract base: frozen, extra="forbid", strict numerics
    catalog.py        CatalogItem (base/form/category), CatalogSnapshot (content-hashed)
    intent.py         structured request; SubstitutionPolicy
    cart.py           asserted_unit_price_paise — the only price field, named for what it is
    mandate.py        the AP2/UAP envelope, modelled locally
    verdict.py        recorded model output with prompt digest and raw response
    decision.py       Outcome, 8 Dimensions, Binding, Decision
    decision_input.py everything decide() may see — including evaluated_at

  ingest/
    units.py          250gm = 1/4 kg = pav kilo; transliterated Hindi quantities
    text.py           price extraction, filler removal, hyphen-as-separator
    taxonomy.py       (base, form, category) placement against the lexicon
    sanitizer.py      rules only; payload detection suppresses the whole field
    loader.py         messy CSV → items, with a LoadReport of every resolution
    snapshot.py       content-addressed snapshots; the narrow agent feed

  intent/             model position #1
    prompt.py         the one prompt, versioned and hashed
    parser.py         IntentParser Protocol; deterministic taxonomy resolution
    recorded.py       recorded answers, keyed on prompt digest
    claude.py         live, structured outputs via output_config.format
    groq_parser.py    the second provider behind the same Protocol

  gate/
    reasons.py        49 reason codes, closed set, each with merchant-facing text
    thresholds.py     versioned, hashed, travels with every decision
    substitution.py   SubstitutionTables + attribute scoring
    binding.py        cart line → requested item, re-derived not trusted
    deterministic.py  six checks that reject on their own authority
    scope.py          scope creep, scored by value
    confidence.py     coverage and margin — computed, never a model's self-report
    semantic.py       model position #2; the tie-breaker, and the replay of recorded ones
    groq_scorer.py    the second provider behind the same Protocol
    decide.py         the pure function, and escalations()
    service.py        orchestration, re-confirmation, settlement authority

  ledger/
    chain.py          append-only, hash-chained, {observed, inferred} envelope
    verify.py         full-chain walk reporting the first break
    store.py          content-addressed artifacts
    replay.py         re-derive from the record; field-level differences

  payments/
    gateway.py        the Protocol — the provider's shape, established by spike
    fake.py           deterministic; enforces the same rules the real one must
    razorpay_client.py  live test mode; refuses a non-rzp_test_ key; signed callbacks

  agent/buyer.py      deliberately naive; matches lexically, on purpose
  api/{app,view}.py   thirteen routes, the decision viewer, and the checkout page

data/fixtures/model_responses.json   28 real model answers, with provenance
scripts/record_fixtures.py           how they were obtained; incremental and resumable
```

## Data flow

```
CSV ──loader──► CatalogItem[] ──snapshot──► CatalogSnapshot (content-hashed)
                                                    │
goal ──ClaudeParser──► payload ──resolve(taxonomy)──► Intent
                                                    │
feed ──NaiveBuyer──► Cart                           │
                       └──────────┬─────────────────┘
                                  ▼
                          DecisionInput  ──► escalations()  ──► [lines needing a model]
                                  │                                      │
                                  │◄───── SemanticVerdict[] ◄────────────┘
                                  ▼
                            decide()  ── PURE ──►  Decision
                                  │
                    ┌─────────────┴──────────────┐
                    ▼                            ▼
            ArtifactStore                  Ledger (hash chain)
            (content-addressed)                  │
                    └──────────► replay() ◄──────┘
```

## The eight dimensions

`PRICE_INTEGRITY` · `BUDGET` · `MERCHANT_SCOPE` · `CATEGORY_SCOPE` · `MANDATE` · `SUBSTITUTION` · `SCOPE_CREEP` · `SANITIZATION`

A `Decision` reports all eight or fails to build. An `APPROVE` carrying any of the 16 blocking reason codes is **unconstructable** — "cart over mandate limit cannot approve" is a property of the type, not a test that samples the ways to violate it.

Weights decide how much a dimension *contributes* to the aggregate. They do not decide whether a failure *counts*: any dimension with status `FAIL` or `UNCERTAIN` caps the outcome at `HOLD`, whatever the average says (ADR-020, BROKE.md 007).

## Ledger

```
seq · event_id · request_id · ts · event_type · payload{observed, inferred} · prev_hash · hash

hash = sha256(canonical({prev_hash, event_id, request_id, ts, event_type, payload}))
```

Hashing a *structure* rather than a concatenation, because `event_type="AB", event_id="C"` and `event_type="A", event_id="BC"` would otherwise produce identical bytes.

`observed` is what the system saw — a catalog price, a gateway response, the JSON a model returned. `inferred` is what it concluded. The envelope is validated on append, so the distinction cannot decay under time pressure.

Events: `INTENT_RECEIVED` · `SNAPSHOT_TAKEN` · `SEMANTIC_VERDICT` · `DECISION_MADE` · `RECONFIRM_REQUESTED` · `RECONFIRM_GRANTED` · `PAYMENT_INITIATED` · `PAYMENT_SETTLED` · `PAYMENT_FAILED`

## API

| Route | Purpose |
|---|---|
| `POST /v1/catalog/ingest` | Normalise the export; reports every resolution it had to make |
| `GET /v1/catalog/feed` | The sanitised agent view — narrower than the snapshot |
| `POST /v1/checkout/verify` | The only route that decides. `Idempotency-Key` required |
| `POST /v1/checkout/confirm/{id}` | A named human authorising a hold. 409 on a rejection |
| `POST /v1/checkout/settle/{id}` | Orders the derived amount, only if authority permits |
| `POST /v1/checkout/capture/{id}` | Takes the payment, only at the amount that was approved |
| `GET /checkout/{id}` | The page a payer completes the order on. Live gateway only |
| `POST /v1/checkout/callback/{id}` | The browser's word, taken only once its signature verifies |
| `GET /v1/ledger/{id}` · `GET /v1/ledger/verify` | The record, and its integrity |
| `POST /v1/replay/{id}` | Re-derive from the record. No model called |
| `GET /view/{id}` · `GET /` | The decision viewer |

No route lets a caller influence *how* a decision is made — only what evidence goes in.

## Storage

SQLite, WAL, one file for the chain and one for artifacts. `BEGIN IMMEDIATE` takes the write lock before reading the head, so concurrent writers cannot fork the chain; a `threading.RLock` covers the same window against threads sharing one connection (BROKE.md 009). Both are needed and neither substitutes for the other.

`Ledger` and `ArtifactStore` are the only things that touch SQL, so the migration path off SQLite is contained to two files.
