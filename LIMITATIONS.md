# Limitations

Stated plainly. A reviewer finds these anyway, and the honest version is shorter than the defence.

## Things that are modelled rather than integrated

**The UPI mandate.** Reserve Pay is not reachable from a self-serve test account, so the mandate is constructed locally and checked deterministically. Every mandate check is real code against a real object; none of it talks to NPCI or an AP2 issuer. What the project demonstrates is the layer *above* the mandate — it consumes one as an input, which is what §8 of the problem statement argues it should do.

**Completing a payment.** Order creation, the payable link, payment fetch and capture are live Razorpay test-mode calls and the payment ids in the ledger are Razorpay's. No API call makes a payment *happen* — a person completes it on a hosted page with a test card — and five contract tests skip on the live gateway for exactly that reason rather than inventing a path that does not exist.

`GET /checkout/{request_id}` serves that page, and `POST /v1/checkout/callback/{request_id}` takes the result. The browser is an untrusted client, so the callback is verified as `HMAC-SHA256(order_id|payment_id)` under the key secret before anything is captured — six tests cover a genuine signature, a forged one, a real signature replayed against a different order, one replayed against a different payment, and one made with the wrong secret.

**The browser leg has been walked.** On 2026-09-04 a verified order was paid on that page in a real browser, end to end: Razorpay's Checkout script executed, a domestic test card went in, the callback came back and its signature verified, and the payment settled for **₹643.00 — the amount the gate derived, not the total the agent asserted**. The record for that request is complete and the chain verifies:

```
INTENT_RECEIVED → SNAPSHOT_TAKEN → DECISION_MADE → PAYMENT_INITIATED → PAYMENT_SETTLED
   pay_TXqSYPMMtBM6te · CAPTURED · 64300 paise · authorised_by=APPROVED · captured_by=razorpay-test
```

To repeat it:

```
make serve                              # with RAZORPAY_KEY_ID in .env
# verify, settle, then open http://127.0.0.1:8000/checkout/<request_id>
# test card 5267 3181 8797 5449 (domestic), any future expiry, any CVV
```

**Use that card, not `4111 1111 1111 1111`.** The international Visa test number is what this page and these documents printed for weeks, and a test account without international payments enabled declines it outright.

Walking it found two defects that no test could have. The server could not serve the page at all — `make serve` ran on the fake gateway, so the documented walkthrough returned 409 at its third line (`BROKE.md` 015). And this account captures automatically, so the payment settled before Custodian's own capture call, which was refused as a duplicate and **wrote nothing** — a settled payment with a trail ending at `PAYMENT_INITIATED` (`BROKE.md` 016). The amount control held throughout; it was the record that was missing.

The Day-5 lesson in `BROKE.md` 006 was that code which only runs against a credential nobody has is code nobody has run. The sharper version, now: a live credential is not sufficient either. It has to be one *configured the way a real merchant's is*, because a fake has no opinion about an account setting.

**Model answers are recorded rather than called, on the default path.** Both positions have two implementations and all four are graded by contract suites against stubs shaped like each provider's real response objects — request shape, schema enforcement, refusals, malformed payloads, truncation, rate limits, and the distinction between a transport failure and a decline. What no stub covers is the network, so `scripts/record_fixtures.py` asked the real thing: **28 responses — 24 substitution verdicts and 4 intent parses — from `openai/gpt-oss-120b` on Groq, recorded 2026-08-30**, each stored in `data/fixtures/model_responses.json` with provider, model, prompt digest, timestamp and the question exactly as sent.

That is not bookkeeping. The first run against real answers instead of hand-written ones broke an abstention guarantee that had held for the whole build, because the fixture I had written for the unplaceable-item case said `UNSURE` and the model — correctly — did not. See `BROKE.md` 012.

What remains deliberate rather than unfinished: `make demo` and the corpus harness **replay** those recordings, because a decision that must reproduce byte-for-byte from the ledger cannot depend on a model answering the same way twice. `make demo-groq` makes the call live, against the same Protocol, and the demo prints which of the three states it is in — live call, real recording, or authored fixture — rather than letting them look alike. A recording names the model that produced it and the verdict carries that id into the ledger; an authored fixture cannot name one.

```
export GROQ_API_KEY=...     # free: console.groq.com
make record                 # re-record; incremental and resumable
make demo-groq              # the same demo, calling live
```

## Things that are unfinished

**The 30 judgment labels rest on one reviewer.** They were drafts for most of this project's life and are now human-signed and attributed, which is what makes the benign-divergence numbers quotable at all. It is still a single pass: 15 distinct substitutions, no adjudication, one catalog — and the reviewer could see the gate's current call while judging, which makes agreement cheaper than an independent pass would be. The harness prints those three bounds itself on every run rather than leaving them to a reader. A second reviewer is the most valuable thing anyone could add here.

**One question the review left open, deliberately.** Two cases phrase the goal as *"or the closest thing you can get"*, and a real model reads that as licence to approve a substitution it otherwise calls unfaithful. The reviewed label holds in both. The gate's channel for "I am flexible" is the `substitution_policy` field, not the goal prose — so whether the intent parser should *infer* policy from phrasing is unresolved, and it would move model position #1 from reading a request to setting the authority a later check runs under. See `EVALUATION.md`.

**Thresholds are `v1-reviewed`, which is a weaker claim than tuned.** No value was ever fitted. What changed is that the reviewed labels made each setting scorable for correctness, and the shipped guess turned out to be the unique agreement peak — 100% at the default, 73–80% at every other setting, holding on DEV and TEST separately. Checked and left alone, not calibrated.

**No allergen or dietary control.** `benign-008` approves groundnut oil for sunflower oil under an `EQUIVALENT` policy, and groundnut is peanut. This system re-derives price, purpose and authority; it has no idea what will hurt someone. That is a different check and a merchant shipping this would need it.

**No pitch recording.** `DEMO.md` is the script; it has not been performed.

## Things that are out of scope by declaration

No authentication, no rate limiting, no multi-merchant, no multi-currency, no dashboard. This is a reference implementation of a verification layer, not a production edge. Adding them would not strengthen the argument and would dilute it.

## Things that would break at scale

**Single writer.** SQLite, one process. `BEGIN IMMEDIATE` plus a mutex makes the chain safe under a threaded server; nothing here survives multiple processes writing one ledger. `Ledger` and `ArtifactStore` are the only modules that touch SQL, so the migration path is contained to two files.

**The lexicon covers one merchant.** 58 bases, 18 form-compatibility pairs, 5 base equivalences, sized to a 70-item catalog. 69 of 70 items place correctly; coverage against a different merchant's catalog is unmeasured. Scaling this is authoring work, not engineering work — which is the honest shape of the problem and the reason it is hard to copy.

**The package assumes an editable install.** `data/catalog` and `data/lexicon` are located relative to `__file__`, so a non-editable install into site-packages would not find them. Shipping them as package data is the fix and is not done — CI and the Makefile both use `pip install -e`, and a merchant-editable lexicon would want to live outside the package anyway.

**The sanitizer is rule-based.** An injection phrased outside its patterns passes it. That is survivable only because the second control is independent: an injected item binds to nothing in the request and is scope creep by construction. The design leans on the second control, not the first.

## Things that are deliberate and might look like gaps

**The buyer agent is bad on purpose.** It matches lexically — the primitive the gate rejects — so it will offer almond milk for coconut milk. Making it clever would undercut the thesis: the claim is that the buying agent is an untrusted client whose competence cannot be assumed, and demonstrating that against a carefully-written agent proves nothing.

**Scope creep holds rather than rejects.** An unrequested item is inside budget, correctly priced and in stock. The human is the authority on whether they want it, and a system that only blocks is one merchants switch off.

**A rejection cannot be re-confirmed.** A genuine false rejection cannot be rescued in flight; it needs a corrected cart, which produces a new decision and a new ledger entry. That is the right shape — the fix leaves a record of what was wrong the first time.
