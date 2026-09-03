# What broke

Kept from the first hour, because the submission form's twelfth field asks what broke and how you got out, and a file written honestly at the end reads like fiction.

Dates are all **2026-08-21**: the whole build happened in four sittings on one day. The "plan phase" numbers map to the problem statement's fifteen-day plan, not to calendar days — see the note at the top of `ENGINEERING_LOG.md`.

Entries are in the order they happened. Nothing is removed once it is fixed.

---

## 001 — Shipped a module with no tests and did not notice

**Plan phase 1 · 2026-08-21 · severity: process, not runtime**

**What broke.** `bp.py` (basis-point scores) went in with a passing smoke test typed into the shell and no test file. The suite was green — 74 passing — because nothing was importing it yet.

**Expected.** A new module lands with tests in the same change.

**Actual.** `pytest --cov` showed `src/custodian/bp.py  40  40  0%`. A whole module at zero coverage, sitting in a green run.

**Symptoms.** None. That is the problem — a green suite that says nothing about the module you just wrote is worse than a red one.

**Root cause.** The shell smoke test *felt* like verification. It exercised the happy path once and was then thrown away, so it left no trace and asserted nothing on the next run. Green suite, unverified code, no signal.

**Fix.** `tests/test_bp.py`, 22 cases including the rejection paths that matter (`0.85` as a float score, out-of-range values, zero denominator, float ratios). Coverage 0% → 90%, total 84% → 94%.

**Why the fix works.** The rejection tests are the point. `bp.validate` exists to stop a float reaching the ledger; a happy-path smoke test would never have exercised that, and the module's whole reason to exist would have been unverified.

**Prevention.** Run `pytest --cov` at the end of each session rather than at the end of the project, and treat a 0% module in a green run as a failure. Cheap now; on day 11 the same gap would surface as an unexplained replay mismatch.

**Lesson.** A smoke test in a shell is a demonstration, not a test. The difference is whether it runs again tomorrow.

---

## 002 — `git push` hung for two minutes and died with no error

**Plan phase 1 · 2026-08-21 · severity: blocked the public repo**

**What broke.** `gh repo create custodian --public --source=. --push` hung and was killed at the 2-minute timeout. No error message, no partial output — just a stall.

**Expected.** Repo created, four commits pushed.

**Actual.** The repo *was* created on GitHub; the push never happened. Worth noting because the failure was split — the API call over HTTPS succeeded, and only the git transport stalled. A quick glance at github.com would have shown a repo and suggested everything worked.

**Symptoms.** Silent hang. Killing the command left a correctly configured `origin` remote pointing at an empty repository, which is the confusing state: everything *looks* wired up.

**Investigation.** Checked in order — repo exists (yes), remote configured (yes, `git@github.com:...`), `github.com` in `known_hosts` (yes, so not a host-key prompt). That ruled out the obvious causes and left the transport itself. Ran `git ls-remote` with `BatchMode=yes` and a 10s connect timeout to force a fast, non-interactive failure:

```
ssh: connect to host github.com port 22: Connection timed out
```

**Root cause.** Outbound TCP port 22 is blocked on this network. `gh` was configured for SSH git operations (`Git operations protocol: ssh`), so every push would hang until TCP gave up — well past any timeout worth waiting through. Campus networks commonly block 22; this is a network policy, not a misconfiguration.

**Fix.** `gh auth setup-git` to register `gh` as the git credential helper, then repoint the remote at HTTPS:

```bash
gh auth setup-git
git remote set-url origin https://github.com/OkayAnshul/custodian.git
git push -u origin main
```

Pushed in seconds. GitHub also serves SSH on port 443 via `ssh.github.com`, which is the alternative if SSH keys are specifically wanted.

**Why the fix works.** HTTPS on 443 is not blocked, and the `gh` token already carries `repo` scope, so no separate credential is needed.

**Prevention.** Diagnose hangs with `BatchMode=yes` and an explicit `ConnectTimeout` rather than waiting them out — it converts a two-minute silence into a one-line error. Default to HTTPS remotes on this network.

**Lesson.** A hang is not less informative than an error, it is just slower to interrogate. Two minutes of waiting produced nothing; ten seconds of asking the right way produced the answer. Also: a partially-succeeded operation is more dangerous than a cleanly failed one, because the visible half looks like success.

---

## 003 — A mandate-expiry check that would pass expired mandates

**Plan phase 2 · 2026-08-21 · severity: would have moved money against a dead mandate**

**What broke.** `Mandate.active_at` compared ISO-8601 timestamps as strings:

```python
return not self.revoked and self.valid_from <= moment < self.valid_until
```

Found by working the comparison by hand before writing its tests, not by a failing run.

**Expected.** A mandate is active only between its start and end instants.

**Actual.** Correct for every timestamp sharing one format — and quietly wrong the moment two formats meet:

```
'2026-08-22T00:00:00+05:30' > '2026-08-22T00:00:00+00:00'   # as strings
                                                             # 5.5 hours EARLIER as instants
```

An IST-stamped `moment` compares as *later* than it actually is. A mandate that expired hours ago passes `active_at`, and the gate approves a spend against dead authority.

**Symptoms.** None available. Every test would have passed, because every timestamp in the tests was already UTC. That is the whole problem: the bug is invisible until a second format arrives, and the natural second format on an Indian project is `+05:30`.

**Root cause.** Two mistakes compounding. `Timestamp` was typed `min_length=20, max_length=40`, which accepts `Z`, `+05:30` and fractional seconds alike — so the type permitted the mixed input. And the comparison assumed lexicographic order matches chronological order, which for ISO-8601 holds only within a single offset and precision.

**Investigation.** Traced from the other direction: the ledger writes `ts` and the gate compares `ts`, so what exactly is a `Timestamp`? The type answered "almost anything ISO-shaped", and the ordering assumption fell out immediately.

**Fix.** `custodian/clock.py` defines one spelling — UTC, second precision, `+00:00`. `Timestamp` enforces it by regex at the schema boundary. `Mandate.active_at` compares parsed instants via `clock.is_before`. `format_utc` refuses naive datetimes rather than assuming UTC. The ledger stopped writing microsecond timestamps.

**Why the fix works.** Two independent layers. The pattern means one instant has one byte sequence, which hashing needs anyway. Parsing means comparison stays correct even if a format slip gets past the pattern. Either alone leaves one failure mode open.

**What changed to prevent recurrence.** `test_the_trap_this_module_exists_for` asserts both halves — that string comparison gets it wrong, and that `clock.is_before` gets it right. The trap is now documented by a test rather than by memory.

**Lesson.** A comparison operator between two strings is not obviously a bug, which is exactly why it survives review. The tell was that the *type* was loose: a field that accepts several spellings of one value will eventually receive two of them. Tighten the type and the ordering question answers itself.

---

## 004 — `¼ kg` normalised to 4000g

**Plan phase 3 · 2026-08-21 · severity: silent 16× error on every pack size written with a vulgar fraction**

**What broke.** `parse_measure("¼ kg")` returned 4000g instead of 250g. No exception — a confident wrong answer.

**Expected.** `¼ kg`, `1/4 kg`, `250gm`, `quarter kilo` and `pav kilo` all normalise to `250g`.

**Actual.** Every other spelling gave 250g. The unicode one gave 4000g.

**Symptoms.** Caught by printing a set of all spellings and seeing two values where there should have been one. A per-item assertion would have passed on thirteen of fourteen cases.

**Root cause.** Ordering. `_normalise_text` ran `unicodedata.normalize("NFKC", …)` *first*, then replaced vulgar fractions. But NFKC has already rewritten `¼` by then — into `1⁄4`, using U+2044 FRACTION SLASH rather than ASCII `/`. So the replacement table never matched, and the quantity regex, which knows only about `/`, matched the trailing `4` as the entire quantity: `4 × 1000 = 4000`.

**Investigation.** One line: `unicodedata.normalize("NFKC", "¼")` → `'1⁄4'`. The character that comes back looks like a slash and is not one.

**Fix.** Expand vulgar fractions *before* NFKC, and map U+2044 and U+2215 to ASCII `/` afterwards as a second line of defence for a fraction that arrives already expanded.

**Why the fix works.** The two passes now cover both entry points — the glyph form and the expanded form — rather than one pass that assumed the glyph would survive to meet it.

**What changed to prevent recurrence.** `test_every_spelling_of_a_quarter_kilo_is_the_same_quantity` parametrises all fourteen spellings against one expected value, so any single spelling drifting is a failure. `test_the_vulgar_fraction_trap` asserts the NFKC behaviour directly, so the reason is documented where it broke.

**Lesson.** A normalisation step is a rewrite, and a rewrite invalidates assumptions made about the text before it. The bug was not in either operation — both were correct — it was in believing the input to the second was the input to the first. Order normalisation passes from most specific to most general, and assert the invariant across the whole equivalence class rather than case by case.

---

## 005 — Bilingual product names failed to place

**Plan phase 4 · 2026-08-21 · severity: silently unplaceable on the most common Indian naming pattern**

**What broke.** Ingesting the real 70-row export, eight items came back `base=UNKNOWN`. Among them: `India Gate Basmati Chawal 1kg`, `Sugar / Cheeni 1kg`, `Onion / Pyaz 1kg`, `Mustard Oil / Sarson ka Tel 1 ltr`.

**Expected.** `rice`, `sugar`, `onion`, `mustard`.

**Actual.** `UNKNOWN` for all four — which routes every substitution involving them to escalation, so the deterministic layer abstains on staples it should settle instantly.

**Symptoms.** No error. Ingest reported 70/70 items built and 62/70 placed, and the eight unplaced looked like an ordinary lexicon-coverage gap. It was only on reading the list that the pattern showed: every one of them named the product twice, once in English and once transliterated.

**Root cause.** `_disambiguate` counted alias *hits* rather than distinct *identities*:

```python
distinct = [(alias, key) for alias, key in base_hits if alias not in form_aliases]
if len(distinct) > 1:
    return UNKNOWN, UNKNOWN
```

"Basmati Chawal" matches two aliases — `basmati` and `chawal` — that both map to base `rice`. The guard was written for genuine ambiguity ("coconut almond blend", two different identities) and could not tell that apart from two spellings agreeing on one identity. Which is worse than a coverage gap, because Indian listings name products bilingually as a matter of course: the richer the transliteration coverage in the lexicon, the *more* items this broke.

**Investigation.** Printed the unplaced list rather than the count. Four of eight shared an obvious shape; adding the aliases would not have helped, since the aliases were already there and were the cause.

**Fix.** Collapse hits to identities before counting:

```python
candidates = {key for _, key in distinct}
if len(candidates) > 1:
    return UNKNOWN, UNKNOWN
```

Also found in the same run: the embedded price was still in the name when placement ran, so `Nestle Everyday Dairy Whitener 400gm ₹235` was matching against residue containing `₹235`. `place()` now strips the price first.

**Why the fix works.** Agreement and ambiguity are now distinguished by what the aliases mean rather than how many of them fired. `coconut almond blend` still resolves to `UNKNOWN` — two identities, no way to pick — which the test asserts alongside the bilingual cases.

**What changed to prevent recurrence.** `test_bilingual_names_place_correctly` covers four real rows from the export, and the ingest test asserts the exact unplaced list rather than a count, so any new item silently dropping out is a failure rather than a number moving.

**Lesson.** The guard was correct for the case it was written against and wrong for a case that looks identical from inside the function. The tell was that improving the lexicon made the failure *more* likely, not less — when adding correct data makes things worse, the bug is in what the code does with agreement.

---

## 006 — The payment interface described a provider that does not exist

**Plan phase 5 · 2026-08-21 · severity: the Day 5 checkpoint was built on a wrong assumption**

**What broke.** `PaymentGateway` had `create_order(...)` then `capture(order)`. Against real Razorpay test-mode credentials, there is no such path. An order nobody has paid has zero payments on it and nothing to capture.

**Expected.** Create an order, capture it, money moves.

**Actual.** Razorpay is `order → (a human pays on a hosted page) → authorized payment → capture(payment_id, amount)`. The gap in the middle is not an API call. No server-side call makes a payment happen.

**Symptoms.** None from the test suite — `FakeGateway` passed the whole contract, because the fake implemented the interface I had imagined rather than the one the provider offers. A fake that satisfies a contract the real thing cannot is worse than no fake: it converts an unknown into false confidence.

**Investigation.** Probed the live API directly rather than reading the SDK's shape and inferring:

```
order.create              -> status=created, amount_paid=0
order.payments(order_id)  -> count=0        <- nothing to capture
payment.capture           -> (payment_id, amount, data)  <- takes a payment, not an order
```

**Fix.** Reshaped the Protocol around what the provider does: `create_order` → `payment_for(order) -> PaymentRef | None` → `capture(payment)`. `FakeGateway` gained `simulate_payer`, which stands in for the human step and is named so it cannot be mistaken for something the live gateway can do. The five contract tests past authorisation now skip on Razorpay with a stated reason instead of silently not existing.

`payment_for` returns whatever state the provider holds rather than filtering for `AUTHORIZED`, because auto-capture is an account setting — a method that only returned authorised payments would report "unpaid" for a perfectly settled order.

**Two further findings from the same spike.**

*`reference_id` is capped at 40 characters.* A Custodian receipt is a request id with no such cap. Shortened inside the gateway by deterministic digest — deterministic because an idempotent retry must produce the same reference, and truncation would collide two long receipts sharing a prefix. A provider's field length should not reach back and dictate our own identifiers.

*Payment Links are rate limited; Orders are not.* Measured, not guessed: six order creations in a burst all succeeded, three payment-link creations succeeded and the fourth returned "Too many requests". The first implementation used links as the per-order primitive, which made a provider rate limit a property of the system. Now orders are the primitive and a link is minted only when a human actually needs to pay. Razorpay also reports rate limiting as a `BadRequestError` — a 400-class exception — so the SDK's own backoff, which keys on status class, does not catch it; the gateway retries it explicitly, since a request refused before anything happened is the one failure that is unambiguously safe to retry.

**Why the fix works.** The interface now has the same shape as the thing behind it, and the asymmetry it cannot remove is marked rather than hidden. `simulate_payer` exists on exactly one implementation, and every test that depends on it says so.

**What changed to prevent recurrence.** `RazorpayGateway` is in the shared contract fixture, so twelve tests now run against the live API on every run with credentials present. The interface can no longer drift from the provider without something going red.

**Lesson.** I designed the interface from the SDK's method names and my expectation of what a payment gateway looks like, then built a fake that agreed with me. Both were self-consistent and both were wrong. The spike was scheduled first precisely because this was the highest-risk unknown — and it stayed unknown through four phases of work because a green suite felt like evidence. A fake is only worth what the real implementation's agreement with it is worth, and that agreement has to be run, not assumed.

---

## 007 — The gate approved an order with a failed dimension

**Plan phase 6 · 2026-08-21 · severity: the exact failure this project exists to prevent**

**What broke.** Running the demo scenarios for the first time:

```
DEMO 3 — almond milk offered for coconut milk
  APPROVE   alignment 85.04%   confidence 83.40%
    SUBSTITUTION  FAIL  34.17%  BASE_CHANGED
```

An `APPROVE` carrying a failed dimension. Also `DEMO 4`, where an unrequested ₹1,450 wok scored 32% on scope creep and approved at 90.80% overall.

**Expected.** A cart containing the wrong ingredient does not approve.

**Actual.** The failure was real, scored correctly, reported correctly — and then averaged away. Substitution carries weight 5 of 22, so a zero on it still leaves the weighted mean above the 80% approve threshold. Seven passing dimensions outvoted the one that mattered.

**Symptoms.** None from the test suite, which did not exist yet for the gate. The dimension breakdown printed the failure plainly and the outcome line said APPROVE two lines above it.

**Root cause.** Two mistakes, one structural and one specific.

The structural one: `_outcome` consulted only the aggregate and a list of blocking reason codes. Weights are meant to decide how much a dimension *contributes*, not whether a *failure counts*. I had written the comment "a constraint that can be outvoted by a good average is not a constraint" inside that very function, and then implemented a function where exactly that happens.

The specific one: `SUBST_BASE_CHANGED` was not in `BLOCKING`, and could not simply be added — the same code fires for a *permitted* equivalence (sunflower oil for groundnut oil under an `EQUIVALENT` policy), so making it blocking would refuse legitimate substitutions. Two different claims were sharing one code.

**Fix.** A new code, `SUBST_BASE_UNRELATED`, for "different identity, no recorded relationship", which is blocking; `SUBST_BASE_CHANGED` stays informational. And a structural guard in `_outcome`: any dimension with status `FAIL` or `UNCERTAIN` caps the outcome at `HOLD`, whatever the average says.

**Why the fix works.** The guard does not depend on anyone maintaining a list correctly. A new dimension added later, or a new failure mode in an existing one, is covered by construction rather than by remembering to register its codes.

**What changed to prevent recurrence.** `test_a_failed_dimension_can_never_be_outvoted_by_a_good_average` asserts both halves — that the aggregate still reads above the approve threshold, *and* that the outcome is nonetheless not `APPROVE`. A test that only checked the outcome would pass again if someone later re-tuned the weights until the average dipped, which would look like a fix and would not be one.

**Lesson.** The scoring was right and the reporting was right; the composition was wrong. Decomposed scores make a system explainable, and they also create a place for a failure to be quietly outvoted — the decomposition needs a rule about which dimensions can veto, and that rule cannot be "whichever ones someone remembered to list". Also: I wrote the correct principle as a comment and then failed to implement it. A comment stating an invariant is a claim, and claims belong in tests.

---

## 008 — A flat sweep that looked like a finding

**Plan phase 8 · 2026-08-21 · severity: would have been reported as a result**

**What broke.** The first threshold sweep produced a completely flat curve, and the alignment sweep produced no rows at all. Flatness is a legitimate outcome, so it read as one: "no threshold changes anything here."

**Expected.** A curve with a bend in it, or a stated reason there is not one.

**Actual.** Two different faults wearing one appearance.

*The alignment sweep produced nothing.* Every point was silently discarded. `Thresholds.version` is capped at 32 characters and the sweep built its version string from the full dial name — `sweep-approve_min_alignment_bp-5000` is 35. Each construction raised, and the `except Exception: continue` that exists to skip settings the invariants forbid swallowed it as though the setting were invalid.

*The confidence sweep was genuinely flat, for a reason that made the measurement useless.* I had excluded the benign-divergence class from the sweep — correctly, since tuning against drafted labels is circular. But that class is the only one whose cases sit near a boundary. What remained was bimodal: clean orders at 100% alignment and violations rejected by deterministic checks. Nothing was near a threshold, so no threshold could move anything.

**Investigation.** The alignment sweep printing a header and zero rows was the tell. A flat curve and an empty curve look similar in a terminal and are not the same failure.

**Fix.** Short version strings (`sw-align-5000`). And a change in what the sweep measures: friction is now reported as the **hold rate on benign-divergence orders**, which needs no ground truth at all — what fraction of plausible substitutions get sent back to a human is a fact about behaviour, not a claim about correctness. Accuracy against labels stays restricted to the derived classes.

**Why the fix works.** It separates the two things that were tangled: *is the gate right* needs labels and is reported only where labels are sound; *how much friction does this setting cost* needs no labels and can therefore be measured across the whole corpus, including the cases whose ground truth is still a draft.

The curve is now real — `substitution_faithful_bp` from 50% to 95% moves substitutions held from 46.67% to 93.33% and the escalation rate from 10.83% to 25.83%, while the adversarial catch rate does not move at all.

**What changed to prevent recurrence.** `test_the_threshold_is_a_dial_with_a_measurable_cost` asserts the curve is monotonic and that its ends differ, so a sweep that silently collapses fails the build.

**Lesson.** A blanket `except Exception: continue` inside a loop that exists to skip invalid inputs will also skip a bug in how the inputs are built, and the output is indistinguishable. And measuring correctness where you only have drafted labels is a dead end — the fix was not better labels, it was finding the question that could be answered without them.

---

## 009 — The ledger could not be used from a web server

**Plan phase 9 · 2026-08-21 · severity: the API did not work at all**

**What broke.** The first request to `POST /v1/checkout/verify` raised:

```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be used
in that same thread.
```

**Expected.** A decision.

**Actual.** Every write failed. The ledger had been correct in tests since the first hour of the build and could not survive being called from a server.

**Root cause.** `Ledger` and `ArtifactStore` open one connection at construction. FastAPI runs synchronous handlers on a threadpool, so the connection was created on the startup thread and used from a worker. Python's `sqlite3` refuses that by default, and rightly — a connection object is not thread-safe.

I had reasoned about concurrency once, on Day 1, and concluded `BEGIN IMMEDIATE` was sufficient. It is, for the problem I was thinking about: two *writers* racing to read the head and append a successor, which would fork the chain. It does nothing about two threads using one connection object, which is a different problem with a similar description. Having solved the first one, I stopped looking.

**Fix.** `check_same_thread=False` on every connection, plus a `threading.RLock` held across the read-head-then-append window and every other statement. Both mechanisms stay: `BEGIN IMMEDIATE` protects the chain against concurrent writers, and the mutex protects the connection object against concurrent users. Neither substitutes for the other.

**Why the fix works.** The lock makes the compound operation atomic within a process. `BEGIN IMMEDIATE` makes it atomic across processes and connections. The chain's invariant — every event's `prev_hash` is its predecessor's `hash` — needs both to hold under a server.

**What changed to prevent recurrence.** `tests/test_api.py` drives every route through `TestClient`, which uses the same threadpool a real server does. A ledger that cannot be called from a handler now fails the suite rather than the demo.

**Lesson.** "I thought about concurrency here" is not the same as "I thought about *this* concurrency here". The Day 1 reasoning was correct and complete for the failure mode I had named, and naming one failure mode is what stopped me finding the second. The tell was that all my tests called the ledger from the thread that made it — every one of them, without exception, which should itself have been suspicious.

---

## 010 — I put three of my own labels in the corpus and marked them human

**Plan phase 9 · 2026-08-21 · severity: the integrity control, defeated by the person who built it**

**What broke.** Testing the new review tool, I wrote a `decisions.txt` with three made-up calls to check the round-trip — including `benign-003: REJECT`, chosen specifically to disagree with the draft so I could see the "differs from the draft" counter move. It worked. Then I rebuilt the corpus expecting a clean slate, and `merge_reviews` correctly preserved all three as `HUMAN`.

**Expected.** A corpus where every benign-divergence label is still marked as a draft awaiting review.

**Actual.** A corpus containing three labels I had invented, indistinguishable in the file from a real human judgment — inside the one class whose entire design exists to keep machine-drafted labels out of the headline numbers.

**Symptoms.** The harness dutifully reported "27 cases awaiting review" instead of 30 and folded the other three into the reviewed set. Everything behaved correctly. Nothing was wrong except the data.

**Root cause.** Two things, and the second is the real one.

`merge_reviews` preserving `HUMAN` labels across a rebuild is correct behaviour — a regeneration must never silently revert a judgment someone made. It has no way to know a judgment was fake.

And the label provenance design recorded *whether* a judgment had been made, not *whose*. `PROPOSED` and `HUMAN` distinguish drafted from reviewed; nothing distinguished reviewed-by-a-person from relabelled-by-whoever-ran-the-tool. I built that gap and then walked into it within ten minutes of building the tool.

**Fix.** `Case.reviewed_by` is required whenever `label_source is HUMAN` — the schema refuses to construct an unattributed human label — and `review.py` requires `--as NAME` before writing one. The three fabricated labels were removed by deleting `cases.yaml` and rebuilding from scratch.

**Why the fix works.** A label now carries the name of whoever made the call. A reviewer who does not know this history can see, per case, that a judgment was attributed to someone — and an unattributed one cannot exist.

**Lesson.** The person most likely to fabricate a label is whoever is closest to wanting the number to look good, and on a solo project that is always the same person. I had been careful about this through every design decision that touched it and careless about it for one minute in a test, which is roughly the ratio that matters. A control that only binds when you remember it is applying to you is not a control — which is the same lesson as BROKE.md 007, arriving from a completely different direction.

---

## 011 — I fabricated the project timeline

**2026-08-21 (found 2026-08-22) · severity: the one class of error this project cannot afford**

**What broke.** `ENGINEERING_LOG.md` carried nine entries headed `Day 1 — 2026-08-21` through `Day 9 — 2026-08-29`. `BROKE.md` and `DECISIONS.md` carried matching dates. Every commit in the repository is timestamped **2026-08-21**, and seven of those nine dates had not yet happened.

**Expected.** A log that records when the work was done.

**Actual.** A log that recorded when the *plan* said the work would be done, written in the past tense, spread across a week that did not occur. Anyone running `git log` finds the contradiction in one command.

**Symptoms.** None from anything automated. The dates were plausible, monotonic, and matched the fifteen-day schedule in the problem statement exactly — which is precisely why they read as real.

**Root cause.** I worked through the plan's phases in one sitting and labelled each phase with the calendar date the plan assigned it, rather than the date it happened. There was no moment of deciding to misrepresent anything; the plan said Day 3 and the plan's Day 3 was 23 August, so the heading said 23 August. Once the first heading was written that way, the remaining eight followed the pattern without the question being asked again.

**Investigation.** Found by comparing the log's headings against `git log --date=format:'%Y-%m-%d'`. Every commit: 21 August, 03:45 to 21:31, four sittings, seventeen hours and forty-six minutes elapsed.

**Fix.** Headings now read `Day N (plan phase) — sitting K, 2026-08-21 HH:MM`, so the plan-phase numbering is kept — it is genuinely how the work was organised — while the dates are the real ones. `BROKE.md` and `DECISIONS.md` dates corrected to 21 August. An unmissable note at the top of the log states the compression outright. Duration claims that had inherited the fiction — "the fake passed for four days", "the ledger was correct for eight days" — were reworded to describe phases of work rather than elapsed days, which is both true and a sharper statement of the lesson.

**Why the fix works.** The record now agrees with the commit history, which is the only timeline anyone can independently check.

**Why this is the worst entry in this file.** Everything Custodian claims rests on the idea that its evidence is honest — that a number in the README was measured, that a decision replays because it was tested, that a drafted label is marked as drafted. A fabricated timeline in the same repository does not just misstate one fact; it gives a reader a reason to discount all the others, including the ones that are carefully true. Technical weaknesses are survivable in a way this is not.

**What changed to prevent recurrence.** The note at the top of the log makes the compression a stated property of the document rather than something a reader must infer. More generally: a date in a document is a claim, and the same rule applies to it as to a number in a README — if it was not observed, it does not get written down as though it was.

**Lesson.** Nothing here was a lie in the moment; it was a plan being transcribed as a record, one heading at a time, with the distinction never surfacing. That is how most fabricated evidence actually gets made. The tell was available the whole time and cost one command to check — and I only ran it because someone asked whether things were working.

---

## 012 — A confident model verdict let an unplaceable item approve

**2026-08-22 · severity: the abstention guarantee, defeated by a correct answer**

**What broke.** Found on the first run with real model responses instead of hand-written ones. `amb-unplaced-001` — the case where the taxonomy cannot place the item at all — went from `HOLD` to `APPROVE`.

**Expected.** An item the system cannot classify holds. That is the whole point of the case, and `SUBST_BASE_UNKNOWN → escalate → hold` is the design's headline example of calibrated abstention.

**Actual.** The escalation went to the model, which was asked whether *"Sparkle Glitter Pens 5 nos"* substitutes for *"glitter pens"* and answered `FAITHFUL` at 9500bp. That is **correct**. They are the same product. And the substitution dimension took the verdict, scored it 9500, passed, and the order approved.

**Symptoms.** None that any test caught, because every fixture until now was written by me and I had written `UNSURE` for that case. My invention preserved the behaviour I expected; the real answer did not. The bug had been present since the escalation path was built and was invisible for as long as the model's answers were mine.

**Root cause.** A category error about what a verdict establishes. The model was asked a question about *similarity* and answered it well. But `base=UNKNOWN` is not a statement that two things might be unalike — it is a statement that the taxonomy could not place the item, and category scope, mandate category coverage and scope-creep binding are all running on `UNKNOWN` downstream. A verdict about similarity does not supply any of that. **A model can tell you two things are alike; it cannot tell you what they are.**

**Fix.** `_substitution_dimension` now tracks whether any line carried `SUBST_BASE_UNKNOWN`, and holds the dimension at `UNCERTAIN` when one did, whatever the verdict says. The guard is narrow on purpose: an escalation for an *unlisted form pair* is still fully resolvable by a verdict, because there the taxonomy did place both items and only the relationship between them was unknown.

**Why the fix works.** It distinguishes the two things escalation currently conflates — "we could not place this" and "we placed both and have no recorded relationship between them." Only the second is a question a model can close.

**What changed to prevent recurrence.** `test_a_confident_verdict_cannot_resolve_an_unplaceable_item` feeds a `FAITHFUL` verdict at 9500bp into exactly that case and asserts the outcome is still `HOLD`, and its sibling asserts the guard does not over-reach into ordinary escalations.

**Lesson.** This is BROKE.md 006 in a different costume. There, a fake gateway satisfied a contract the real provider could not, and it passed for four phases of work because nobody had run the real thing. Here, hand-written fixtures satisfied an abstention guarantee that a real model broke on the first call — and for the same reason: **a stand-in written by the person who also wrote the expectations agrees with them.** It is not a test until something you did not author has a chance to disagree.
---

## 013 — The demo's payable link worked exactly once

**2026-09-03 · severity: the first thing a viewer sees, broken in a way only a second run reveals**

**What broke.** `make demo` with live credentials printed, where the payable URL belongs:

```
settlement: razorpay-test  order order_TXYMaKCb89wkPk  ₹698.00
            link unavailable: razorpay: could not create payment link: BadRequestError: pa
```

**Expected.** A URL — the moment in the demo where the amount Custodian derived becomes something a person could actually pay.

**Actual.** A truncated error, on every run of the demo after the first one ever made.

**Root cause.** Razorpay's `reference_id` on a payment link reads like an idempotency key and is not one: it is a uniqueness constraint. `payment_link_for` mints under `"<receipt>-link"`, the demo's receipt is the constant `demo-1`, so the first run created `demo-1-link` and every run since was refused with *"payment link with given reference_id: demo-1-link already exists"*.

The code that chose a stable reference did so deliberately, and its docstring gives the reason: an idempotent retry must produce the same reference. That is correct for **orders**, where the provider treats the receipt as idempotent. It is wrong for **links**, where the same field name means something else. One field, two meanings, and I had reasoned about only the first.

**Symptoms.** None in the suite. `payment_link_for` is not part of the `PaymentGateway` Protocol — only one of the two implementations can mint a link — so no contract test covers it. And the demo catches the exception and prints a short line, which is the right behaviour and also the reason this never looked like a failure: a path that degrades politely reads the same on the tenth run as on the first.

**Investigation.** The truncation was the tell — sixty characters is not enough to read a provider error, and `BadRequestError: pa` is not a message. Replaying the payload against the API directly returned the full text; a minimal payload without `reference_id` succeeded. Two calls.

**Fix.** A duplicate reference now falls through to the link that already exists, on two conditions: the amount must equal the amount this order re-derived, and the link must still be payable. A link minted for a different total under the same receipt, or one already `paid`, raises instead — returning either would charge the wrong amount or invite a second payment for an order already settled. Separately, `POST /v1/checkout/settle` no longer lets a refused link fail the settlement: the order is open and the amount is fixed, so the response carries `payment_url: null` rather than a 500. ADR-031.

**Why the fix works.** It stops treating one provider field as though it meant the same thing in two places. Where the provider offers idempotency — order receipts — the stable reference is kept, because that is what makes a retry safe. Where it offers uniqueness, the object that already exists is looked up rather than fought with.

**What changed to prevent recurrence.** `tests/test_payment_link_reuse.py` — a first mint creates; a second returns the existing link; a link for a different amount is never handed back; a `paid`, `cancelled` or `expired` link is not reused; a failure that is not a duplicate still raises rather than becoming a lookup; and a listing entry with no usable amount is skipped rather than trusted. `tests/test_api.py` covers the settle path surviving a gateway that will not mint at all.

**Lesson.** BROKE.md 006 arriving a third time from the same direction: the parts that only run against real credentials are the parts nobody has run. What made this one slower to see is that it *had* run — once, successfully, when the code was written — and nothing afterwards was a fresh account. **A failure that only appears on the second run is invisible to a suite that starts clean every time**, and it is exactly the failure a demo hits, because a demo is by definition the second run.
---

## 014 — The build was red for ten runs and I read it as noise

**2026-08-21 (found 2026-09-03) · severity: the check that guards every number, unable to pass**

**What broke.** CI's last step compares the committed `eval/corpus/cases.yaml` against a fresh `python -m eval.corpus.build`, so that a corpus which has drifted from its own generator fails the build rather than quietly grading everything. It failed on every push from *"Second pass on the 30 judgment labels"* onward — ten consecutive runs, 21 August to 3 September:

```
X cases.yaml is out of date — run python -m eval.corpus.build
```

**Expected.** A rebuild reproduces the committed corpus.

**Actual.** It could not, ever, from the moment the second pass was recorded.

**Root cause.** `merge_reviews` preserved labels marked `HUMAN` across a regeneration and dropped everything else. The second pass writes `MACHINE_REVIEWED` — a distinct source on purpose, so a model's review can never be counted as a human's (ADR-029, and `BROKE.md` 010, which is why the distinction exists at all). So a rebuild reverted all 30 to `PROPOSED` and dropped their `reviewed_by`, and the file on disk could never match a fresh build.

Every other CI step passed the whole time. The tests, the corpus, the sweep, the counterfactual and the demo were green on all ten of those runs.

**Symptoms.** A red badge, and a `git push` that ends the same way whatever you changed. Nothing local ever failed: `make check` does not run the staleness comparison, so the whole build was green on my machine on every one of those thirteen days.

**Investigation.** Found while running CI's steps by hand before submission — not from the badge, which I had been looking at for eleven days. `gh run list` showed the failure starting at exactly the commit that introduced `MACHINE_REVIEWED`, which named the cause before the log was read.

**Fix.** `merge_reviews` now preserves both reviewed sources. That is the same rule it always stated rather than a weakening of it: both carry a reviewer's name, and dropping either on a rebuild loses attributed work. The distinction survives the merge — a machine-reviewed label is still reported as awaiting human review, it is just no longer thrown away.

**Why the fix works.** It makes the file and its generator agree, which is the property the CI step exists to assert. `test_the_committed_corpus_is_what_the_generator_produces` now asserts it locally too, so the failure surfaces in `make test` instead of only in a place I had learned to ignore.

**Lesson.** A check that cannot pass is indistinguishable from one that always fails, and after the second red run I stopped reading it. Worse, the thing it was protecting was real: the corpus in the repository was not the corpus the code produced, which is the exact condition that makes every number resting on it unverifiable — and the check was telling me so, correctly, ten times. The tell was that the build went red on a specific commit and stayed red; a flaky build wanders, a broken invariant does not. And the local shortcut is what let it run: `make check` was "what CI runs" in every document, and it was not.
