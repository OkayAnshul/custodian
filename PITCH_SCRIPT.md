# The pitch — three surfaces, 6:09

**Read the `SAY` blocks aloud. Do the `DO` lines.** Every word is checked against the
repository, so you cannot overclaim by reading it.

The design principle: **each surface does only what it alone can do.**

| Surface | What it is for | Minutes |
|---|---|---|
| **pitch mode** (the site) | The argument — the collision, the gap, the numbers | 2:36 |
| **the terminal** (`make live`) | The proof — it runs, and real money moves | 2:24 |
| **GitHub** | The credibility — seventeen failures, green CI, a real repo | 0:39 |

Nothing is shown twice. The site never demos what the terminal proves; the terminal never
argues what the site states.

---

## Setup — before you press record

```bash
cd ~/Buildathon-Razorpay
make pitch
```

Then arrange **four things** and do not touch the layout again:

| | What | Where it comes from |
|---|---|---|
| **Tab 1** | pitch mode | opened by `make pitch` |
| **Tab 2** | the checkout page for paying | URL printed by `make live`, opened in §3 |
| **Tab 3** | `github.com/OkayAnshul/custodian` | open it yourself now |
| **Terminal** | where `make pitch` runs | you will type `make live` into it |

**Keys in pitch mode:** `→` next · `←` back · `N` notes · `T` timer · `/` questions · `F11` fullscreen.

**Decide before recording:** capture the *whole screen* and your `N` notes are visible to
viewers; capture *just a window* and they are private, but you cannot switch surfaces. **For
this pitch you need the whole screen** — so keep notes off, or accept that they show.

**The safety net.** Before recording, run `make live` once all the way through and pay it.
That proves the path works today *and* leaves a settled decision in the viewer you can fall
back to if the live payment stalls on camera.

---

---

## How to hint the architecture without lecturing

**Never say "let me walk you through the architecture."** The moment you do, you are asking for
four minutes you do not have, and the room stops watching the screen.

Instead: **every architectural claim is delivered as the reason the screen looks like that.**
One clause, attached to something they can already see. The architecture arrives as an
explanation of evidence rather than as a diagram.

| What is on screen | The clause that hints the architecture |
|---|---|
| 70 rows become 70 items | "…content-hashed, so every later price check is relative to *that* snapshot" |
| The agent feed | "…the agent gets a narrower view than the system holds. That is a trust boundary, not a convenience" |
| `REJECT`, nothing escalated | "…deterministic checks run first and can refuse on their own authority, so a bad cart never reaches a model" |
| Confirm refused | "…the three outcomes differ in *kind*. Policy lives in infrastructure, not in anyone's discretion" |
| `HOLD` at 90% | "…one failed dimension caps the outcome. Weights decide contribution, not whether a failure counts" |
| The order amount | "…it opens for the figure the server re-derived. The agent's number never reaches the gateway" |
| The chain | "…every entry separates what was *observed* from what was *inferred*" |
| Replay | "…the model's answer was recorded as evidence, so the decision replays without calling it again" |

That is the whole architecture — eight clauses, none longer than a breath, each one answering
"why does it look like that?"

**If someone asks "so what is it?"** — two sentences, never one:

> Custodian is a merchant-side layer that treats an AI buyer as an untrusted client. Before
> money moves it re-derives the purchase against the merchant's own catalog and the user's
> mandate, and writes the decision to a tamper-evident ledger.

*Do not open with this.* It is a definition, and a definition closes the gap a good opening is
trying to create. Lead with the 0.3333 collision — something concrete the room snags on — and
let them ask for the category.

**If someone asks for the architecture directly,** give them the two-kinds-of-correctness frame
and stop. *(This block is for questions — it is not part of the timed run below.)*

> There are two kinds of correctness here. **Mechanical** — is the price right, is it inside
> budget, is the mandate live. Computers are perfect at that, so it is integer arithmetic and
> set membership, and it can reject on its own authority. And **semantic** — is coconut cream a
> reasonable stand-in for coconut milk. That is genuinely language, so it is a table lookup
> first, and a model only where the table has nothing to say. The whole design is that split,
> and which side of it each question falls on.

Then offer the repo. Do not draw the diagram unless they ask twice.

# 0 · Open — 1:08   `SITE`

**DO** — Tab 1, press `→` twice to **beat 2**.
**POINT AT** — nothing at first: look at the room. Then `0.3333` on "identically".

> In March, Razorpay and Sarvam shipped a voice agent that pays **without a PIN**, with Swiggy
> as launch partner. Razorpay's own position is that agentic shopping doesn't rewrite
> commercial liability — so when that agent orders the wrong thing, **the merchant** eats it.
>
> This track names the stack: MCP for communication, UCP and ACP for commerce, AP2 and UAP
> for authorization, x402 and UPI for settlement. All four solved or being solved — and
> **none of them asks whether the purchase was what was asked for.** Reserve Pay proves the
> agent was allowed to spend. Vulcan asks if the payment is genuine. Nothing asks this. And
> the gap sits exactly where Razorpay does — at the merchant.
>
> I'm Anshul. Custodian does exactly what this track asks: **make an Indian merchant
> transactable by an AI buyer end to end — then verify the agent bought what the human
> actually asked for.**
>
> Two jobs. It ingests a messy real-world catalog and emits an agent-readable feed. And it
> treats that buyer as an **untrusted client** — every claim re-derived server-side before
> money moves, every decision written to a tamper-evident ledger.
>
> The principle underneath it: **policy enforcement lives in infrastructure, never in a
> prompt.**

**Pause two seconds.**

---

# 1 · Why it's hard — 31s   `SITE`

**POINT AT** — the two sides of the `0.3333` panel.

> Here's the hard part. Coconut milk is out of stock. An agent substitutes coconut cream —
> fine. Almond milk — not fine. **Text similarity scores those two identically.** Same number,
> opposite answers. So you can't solve this by reading the agent's output more carefully.
>
> But you already know the shape of the fix: you'd never trust a browser that posted its own
> price. You look it up server-side. **An agent is just another untrusted client** — nobody
> has been treating it like one.

---

# 2 · The growth half — 28s   `SITE`  ← the track's own word

**DO** — press `→` to **beat 1**, the transactability chart.
**POINT AT** — the `18` bar, then the `69`.

> And this track is **AI Growth** and agentic commerce, so here's the growth half.
>
> A merchant whose catalog an agent can't read gets **zero** agentic orders. Not fewer — zero.
> Seventy rows of a real kirana export: an AI buyer can act on **eighteen**. After ingest,
> **sixty-nine**.
>
> That's the revenue argument. Making a store transactable is what puts it in the market at
> all — and verification is what lets the merchant leave it switched on.

---

# 3 · How it decides — 28s   `SITE`  ← the differentiator

**DO** — press `←`, scroll to the four decomposition rows.
**POINT AT** — the blue `coconut` chips, then `almond`.

> Every product, in the catalog and the request, breaks into a base ingredient and a form.
> Coconut, milk. Coconut, cream — same base, listed pair, faithful. Almond, milk — different
> base, no relationship, rejected.
>
> Arithmetic, against a hand-authored **Indian** grocery lexicon: transliterated pack sizes,
> bilingual names. **No model called for either.** A model is asked only where the tables
> genuinely can't decide — twenty-four of a hundred and sixty-two cart lines. **Zero
> adversarial cases.**

---

# 4 · Watch it run — 1:24 talking, plus the payment   `TERMINAL`  ← the proof

**DO** — switch to the terminal. Type where they can see: `make live`

> The merchant's real export — empty price column, stock spelled four ways. Seventy rows in,
> seventy items out, content-hashed, so every later check is relative to *that* snapshot.
>
> This is what the agent may see. Never the raw description — that's where injection lives.
>
> Now the agent builds a cart: ninety-nine rupees for a one-ninety-nine item, plus a
> fourteen-fifty wok nobody asked for.

**Let the REJECT land.**

> **Rejected** — on arithmetic. And notice nothing escalated: deterministic checks run first
> and refuse on their own authority, so a bad cart never reaches a model.
>
> Now a human tries to confirm it anyway — **refused.** A constraint you can wave through is
> advisory. So the agent resubmits, corrected. The price is right; the wok isn't. That
> **holds** — and the human completes it, while the record still reads hold, naming who
> overrode it. That's the number a false-hold rate is measured from.
>
> Real Razorpay order — two thousand ninety-three rupees, **the figure the server re-derived.**

**DO** — open the checkout URL, pay with `5267 3181 8797 5449`.

> It stops here because no API call does this step. Someone puts a card in. That's the honest
> gap, and I'd rather stand in it than hide it.

**DO** — come back as the chain prints.

> Settled. Each entry's hash is the next one's parent — and it replays byte for byte with the
> model client mocked to raise if anything calls it, because the model's answer was recorded
> as evidence rather than re-asked.

---

# 5 · What it's worth — 36s   `SITE`

**DO** — Tab 1, `→` to **beat 5**.
**POINT AT** — the peak at 80%, and the fall-off both sides.

> A hundred and twenty orders: thirty-one thousand six hundred rupees stopped or held — and
> **zero of sixty clean orders held.** No friction on the orders that were fine, which is the
> number that decides whether a merchant keeps it on.
>
> This threshold was a guess. Thirty labels are cooking judgments a model can't honestly
> supply, so I reviewed them by hand and signed each one — and the guess turns out to be the
> **only** setting that agrees completely. Falls off both sides. Holds on both halves of the
> split. Not one value moved.

---

# 6 · Why believe it — 33s   `GITHUB`

**DO** — Tab 3. The green CI badge, then click **`BROKE.md`**.

> Public repo, runs from a clean clone with no credentials, five hundred and fifty-seven
> tests green.
>
> And this is the file I'd read first. Seventeen failures with root causes — fifteen found by
> running the real thing rather than reasoning about it. Including one this week where a
> payment settled and the ledger didn't record it, because the account auto-captures and my
> capture arrived second. **Money moved without a record.** That's the one thing this ledger
> may not do, and it's written down rather than quietly fixed.

---

# 7 · Close — 25s

> Everything in the stack proves the agent was **allowed** to spend. Custodian is the first
> thing that checks it bought the **right thing** — with arithmetic, not a model's opinion.
>
> And the number to push on is my hundred percent agreement: one reviewer, me, no
> adjudication, one catalog, who could see the gate's answers while judging. The harness
> prints those caveats itself, every run.
>
> Thank you.

---

## Timing

| § | Surface | Measured |
|---|---|---|
| 0 · The track's ask, the gap, what this is | site | 1:08 |
| 1 · Why it's hard | site | 0:31 |
| 2 · **The growth half** | site | 0:28 |
| 3 · How it decides | site | 0:28 |
| 4 · **Live run** | terminal | 1:24 talking |
| 4 · the payment itself | browser | ~0:30 |
| 5 · What it's worth | site | 0:36 |
| 6 · Why believe it | github | 0:33 |
| 7 · Close | either | 0:25 |
| | | **6:09** including the payment |

Counted from the words at 160 a minute, not estimated.

### If you need less

| Target | Drop | Lands at |
|---|---|---|
| **5:30** | §1 — the collision is on screen, so point at it and say only *"same number, opposite answers"* | ~5:38 |
| **5:00** | …and the four-layer list in §0 — say *"every layer of this stack proves permission; none asks purpose"* | ~5:05 |
| **4:30** | …and the live payment: *"I have one settled from earlier"*, then show the finished chain | ~4:30 |

**Never cut:** §2 (growth is the track's own word), §3 (the differentiator), the
confirm-refused moment in §4, or the self-criticism in §7.

---

## After — the questions

Press `/` in pitch mode, type a word: 28 anticipated questions with answers. `Esc` closes.

Rehearse this one out loud until it sounds like you mean it: *"Your corpus scores 100% —
isn't that suspicious?"* Agree instantly, produce the threshold peak underneath it, then give
the three bounds before they ask.

**If any screen dies:** `okayanshul.github.io/custodian` has every number and screenshot.
Keep talking.
