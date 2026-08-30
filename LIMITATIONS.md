# Limitations

Stated plainly. A reviewer finds these anyway, and the honest version is shorter than the defence.

## Things that are modelled rather than integrated

**The UPI mandate.** Reserve Pay is not reachable from a self-serve test account, so the mandate is constructed locally and checked deterministically. Every mandate check is real code against a real object; none of it talks to NPCI or an AP2 issuer. What the project demonstrates is the layer *above* the mandate — it consumes one as an input, which is what §8 of the problem statement argues it should do.

**Completing a payment.** Order creation, the payable link, payment fetch and capture are live Razorpay test-mode calls and the payment ids in the ledger are Razorpay's. No API call makes a payment *happen* — a person completes it on a hosted page with a test card — and five contract tests skip on the live gateway for exactly that reason rather than inventing a path that does not exist.

`GET /checkout/{request_id}` now serves that page, and `POST /v1/checkout/callback/{request_id}` takes the result. **The signature check on that callback is tested; the page itself is not.** The browser is an untrusted client, so the callback is verified as `HMAC-SHA256(order_id|payment_id)` under the key secret before anything is captured — six tests cover a genuine signature, a forged one, a real signature replayed against a different order, one replayed against a different payment, and one made with the wrong secret. What no test covers is a browser actually loading the page and Razorpay's script driving it, because that needs a browser. It is marked here rather than claimed:

```
make serve                              # with RAZORPAY_KEY_ID in .env
# verify, settle, then open http://127.0.0.1:8000/checkout/<request_id>
# test card 4111 1111 1111 1111, any future expiry, any CVV
```

Until someone runs that, treat the hosted page as written-and-unrun. The Day-5 lesson in `BROKE.md` 006 was precisely that code which only runs against a credential nobody has is code nobody has run.

**No model call has been made live.** *(`make record` fixes this in one command once a key exists — see below.)* Both positions have two implementations and all four are graded by contract suites against stubs shaped like each provider's real response objects — request shape, schema enforcement, refusals, malformed payloads, truncation, rate limits, and the distinction between a transport failure and a decline. What none of that covers is the network. Until a key is present and the fixtures are recorded, `RecordedParser` and `RecordedScorer` are replaying answers that were written rather than received, and the class names overstate what happened.

`scripts/record_fixtures.py` closes that: 23 distinct substitution questions across the corpus plus 2 intent parses, made for real and written to `data/fixtures/model_responses.json` with provenance — provider, model, prompt digest, timestamp and the question as sent. It is incremental and resumable, so a rate limit mid-run does not lose the recordings already made.

The distinction survives afterwards. A real recording names the model that produced it and the verdict carries that id into the ledger; an authored fixture cannot name one, and reports `recorded`. The demo prints which of the three states it is in — live call, real recording, or authored fixture — rather than letting them look alike.

```
export GROQ_API_KEY=...     # free: console.groq.com
make record                 # 25 calls
```

## Things that are unfinished

**30 corpus labels are drafts.** The benign-divergence class is the project's stated moat and it is the one part a model cannot honestly supply: scored against labels it drafted, it measures its own consistency. The schema refuses to build a benign-divergence case with a derived label, the harness reports them separately, and no headline number rests on them. `python -m eval.corpus.review --sheet` lays out the evidence for each.

**Thresholds are `v0-untuned`.** They are stated guesses, labelled as such in the source. The sweep now says exactly what tuning them would cost — and that tightening buys no catch rate on this corpus, only friction. Real tuning needs the reviewed labels.

**No pitch recording.** `DEMO.md` is the script; it has not been performed.

## Things that are out of scope by declaration

No authentication, no rate limiting, no multi-merchant, no multi-currency, no dashboard. This is a reference implementation of a verification layer, not a production edge. Adding them would not strengthen the argument and would dilute it.

## Things that would break at scale

**Single writer.** SQLite, one process. `BEGIN IMMEDIATE` plus a mutex makes the chain safe under a threaded server; nothing here survives multiple processes writing one ledger. `Ledger` and `ArtifactStore` are the only modules that touch SQL, so the migration path is contained to two files.

**The lexicon covers one merchant.** 56 bases, 24 form-compatibility pairs, 5 base equivalences, sized to a 70-item catalog. 69 of 70 items place correctly; coverage against a different merchant's catalog is unmeasured. Scaling this is authoring work, not engineering work — which is the honest shape of the problem and the reason it is hard to copy.

**The package assumes an editable install.** `data/catalog` and `data/lexicon` are located relative to `__file__`, so a non-editable install into site-packages would not find them. Shipping them as package data is the fix and is not done — CI and the Makefile both use `pip install -e`, and a merchant-editable lexicon would want to live outside the package anyway.

**The sanitizer is rule-based.** An injection phrased outside its patterns passes it. That is survivable only because the second control is independent: an injected item binds to nothing in the request and is scope creep by construction. The design leans on the second control, not the first.

## Things that are deliberate and might look like gaps

**The buyer agent is bad on purpose.** It matches lexically — the primitive the gate rejects — so it will offer almond milk for coconut milk. Making it clever would undercut the thesis: the claim is that the buying agent is an untrusted client whose competence cannot be assumed, and demonstrating that against a carefully-written agent proves nothing.

**Scope creep holds rather than rejects.** An unrequested item is inside budget, correctly priced and in stock. The human is the authority on whether they want it, and a system that only blocks is one merchants switch off.

**A rejection cannot be re-confirmed.** A genuine false rejection cannot be rescued in flight; it needs a corrected cart, which produces a new decision and a new ledger entry. That is the right shape — the fix leaves a record of what was wrong the first time.
