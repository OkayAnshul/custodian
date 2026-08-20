# What broke

Kept from day 1, because the submission form's twelfth field asks what broke and how you got out, and a file written honestly on day 15 reads like fiction.

Entries are in the order they happened. Nothing is removed once it is fixed.

---

## 001 — Shipped a module with no tests and did not notice

**Day 1 · 2026-08-21 · severity: process, not runtime**

**What broke.** `bp.py` (basis-point scores) went in with a passing smoke test typed into the shell and no test file. The suite was green — 74 passing — because nothing was importing it yet.

**Expected.** A new module lands with tests in the same change.

**Actual.** `pytest --cov` showed `src/custodian/bp.py  40  40  0%`. A whole module at zero coverage, sitting in a green run.

**Symptoms.** None. That is the problem — a green suite that says nothing about the module you just wrote is worse than a red one.

**Root cause.** The shell smoke test *felt* like verification. It exercised the happy path once and was then thrown away, so it left no trace and asserted nothing on the next run. Green suite, unverified code, no signal.

**Fix.** `tests/test_bp.py`, 22 cases including the rejection paths that matter (`0.85` as a float score, out-of-range values, zero denominator, float ratios). Coverage 0% → 90%, total 84% → 94%.

**Why the fix works.** The rejection tests are the point. `bp.validate` exists to stop a float reaching the ledger; a happy-path smoke test would never have exercised that, and the module's whole reason to exist would have been unverified.

**Prevention.** Run `pytest --cov` at the end of each session rather than at the end of the project, and treat a 0% module in a green run as a failure. Cheap now; on day 11 the same gap would surface as an unexplained replay mismatch.

**Lesson.** A smoke test in a shell is a demonstration, not a test. The difference is whether it runs again tomorrow.
