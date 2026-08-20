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

---

## 002 — `git push` hung for two minutes and died with no error

**Day 1 · 2026-08-21 · severity: blocked the public repo**

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

**Day 2 · 2026-08-22 · severity: would have moved money against a dead mandate**

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
