# The pitch — three surfaces, six minutes as written

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

# 0 · Open — 1:20   `SITE`

**DO** — Tab 1, press `→` twice to **beat 2**. Start here, not at the beginning.
**POINT AT** — nothing for the first sentence: look at the room, not the screen. Then the big
`0.3333` in the middle on "identically".

> In March, Razorpay and Sarvam shipped a voice agent that completes payments **without a
> PIN**, with Swiggy as launch partner. And Razorpay's stated position is that agentic
> shopping doesn't rewrite commercial liability — so when that agent orders the wrong thing,
> **the merchant** handles the dispute.
>
> Reserve Pay proves the agent was allowed to spend. Vulcan asks whether the payment is
> genuine. The Dispute Auto-Responder cleans up afterwards. **Nothing asks whether the
> purchase was what the human actually asked for.**
>
> I'm Anshul. **Custodian is a merchant-side layer that treats an AI buyer as an untrusted
> client** — it re-derives what the agent claims against the merchant's own catalog and the
> user's mandate, and records the decision in a tamper-evident ledger, before money moves.
>
> **Here's why that's harder than it sounds.** Coconut milk is out of stock. An agent offers
> coconut cream — fine. It offers almond milk — not fine. The obvious check is text
> similarity, and text similarity scores those two **identically**. Point three three three,
> both. Same number, opposite answers.
>
> You already know the shape of the fix, though: you'd never trust a browser that posted its
> own price — you look it up server-side. **An agent is just another untrusted client**, and
> nobody has been treating it like one.

**Pause two seconds after "treating it like one."** That is the beat where the room decides
whether this is a guardrail demo or something else — give it the silence.

---

# 1 · Where each layer stops — 36s   `SITE`

**DO** — press `←` twice to **beat 0**.
**POINT AT** — the empty **Purpose** row. (The `SHIPPED · MARCH` card is already spent — you
opened on it.)

> Four layers. Three are solved — MCP for talking to systems, ACP and UCP for building a
> cart, AP2 and UAP for proving the agent was **permitted** to spend. Every one stops before
> the question of *what* was bought, and that's deliberate: a payment rail shouldn't be
> adjudicating whether coconut cream is an acceptable substitute. Which means the check has
> to happen at the merchant.
>
> So this checks **purpose alignment, not fraud** — and it treats both sides as untrusted: the
> buying agent for what it claims, and the merchant's own catalog text for what it contains.

---

# 2 · How it decides — 43s   `SITE`  ← the differentiator

**DO** — press `→` twice to **beat 2**, scroll past the collision to the decomposition rows.
**POINT AT** — the blue `coconut` chips on rows one and two, then `almond` on row three.

> Every product — in the catalog and in the request — breaks into a base ingredient and a
> form. Coconut milk is coconut, milk. Coconut cream is coconut, cream: same base, and
> milk-to-cream is a listed pair. Faithful. Almond milk is **almond** — different base, no
> recorded relationship. Rejected.
>
> Arithmetic, against a hand-authored **Indian** grocery lexicon: transliterated pack sizes,
> `pav kilo` and `¼ kg` and `250gm` all resolving to one quantity, bilingual product names.
> **No model called for either of those.** A generic guardrail wrapper has none of it.
>
> A model is asked only when the tables genuinely can't decide — that fourth row. Twenty-four
> of a hundred and sixty-two cart lines. Zero adversarial cases.

---

# 3 · Now watch it run — 2:27 of talking, plus the payment   `TERMINAL`  ← the proof

**DO** — switch to the terminal. Type it where they can see:

```bash
make live
```

Narrate over it. One line per stage — the script pauses for you.

> This is the merchant's actual export. Empty price column, stock spelled four ways, pack
> sizes living inside the product name.
>
> Seventy rows in, seventy items out, and it names every resolution it had to make —
> content-hashed, so every later price check is relative to *that* snapshot. One item it
> can't place, and that one escalates rather than guesses.
>
> Here's what the agent is allowed to see — and note there are **two** untrusted parties in
> this system, not one. The agent is untrusted for what it claims. But the merchant's own
> catalog text is attacker-controlled too, because no merchant writes every word in their own
> feed — so the agent never gets the raw description, which is where injection lives.
>
> Now an untrusted agent builds a cart. It asserts ninety-nine rupees for an item the catalog
> prices at one ninety-nine, and it adds a fourteen-fifty wok nobody asked for.

**PAUSE — let the `REJECT` land.**

> **Rejected** — on arithmetic, not on a model's opinion. It asserted eighteen ninety-three;
> the catalog says twenty ninety-three. And notice nothing escalated: deterministic checks run
> first and can refuse on their own authority, so a bad cart never reaches a model.
>
> And now watch a human try to confirm it anyway — **refused.** A constraint you can wave
> through is advisory. So the agent has to come back with a corrected cart.
>
> Price fixed. The wok is still there, and that's a judgment a human owns, so it **holds**
> rather than refusing. The human confirms *that* — and the record still reads hold, with a
> separate entry naming who overrode it. "Held, then a human said yes at 14:32" is the
> truthful entry, and it's the number a false-hold rate is measured from.
>
> Real Razorpay order, opened for two thousand and ninety-three rupees — **the figure the
> server re-derived.** The agent's number never reaches the gateway at all.

**DO** — the script prints a checkout URL and **waits**. Open it in Tab 2. Pay with
`5267 3181 8797 5449`, any future expiry, any CVV.

> And it stops here, because no API call performs this step. Someone has to put a card in.
> That's the honest gap in the system and I'd rather stand in it than hide it.

**DO** — pay. Come back to the terminal as it prints the settled chain.

> Settled. And there's the whole trail — intent, snapshot, decision, the human's override,
> the order, the payment. Each entry's hash is the next one's parent, so you can't edit one
> without breaking the chain. It replays byte for byte with the model client mocked to raise
> if anything calls it.

*If the payment stalls: Ctrl-C, switch to the decision you settled before recording, and say
"here's one from earlier — same path." Do not wait on camera.*

---

# 4 · What it's worth, and what it costs — 41s   `SITE`

**DO** — back to Tab 1, press `→` to **beat 5**.
**POINT AT** — the peak at 80%, and the fall-off on *both* sides.

> Across a hundred and twenty orders: thirty-one thousand six hundred rupees stopped or
> held — and **zero of sixty clean orders held.** The cost in the same breath, because a
> saving without its cost is advertising.
>
> This threshold was a guess when I shipped it. Thirty of my test labels are cooking
> judgments a model can't honestly supply, so I reviewed them by hand and signed each one.
> That made this measurable — and the guess turns out to be the **only** setting that agrees
> completely. Falls off both sides. Holds on both halves of the split separately.
>
> Not one value moved. So the version string says reviewed, not tuned.

---

# 5 · Why you can believe any of it — 39s   `GITHUB`

**DO** — switch to Tab 3. Show the README top — the green CI badge — then click **`BROKE.md`**
and scroll.

> Everything I've said is in a public repo that runs from a clean clone with no credentials.
> Five hundred and fifty-seven tests, green.
>
> And this is the file I'd actually read first. Seventeen failures, written as they happened,
> with root causes. Fifteen of the seventeen were found by running the real thing rather than
> reasoning about it — including the last one, this week, where a payment settled and the
> ledger didn't record it, because the account auto-captures and my capture arrived second.
>
> Money moved without a record. That's the one thing this ledger may not do, and it's written
> down rather than quietly fixed.

---

# 6 · Close — 26s   `SITE or GITHUB`

> Everything in the stack proves the agent was **allowed** to spend. Custodian is the first
> thing that checks it bought the **right thing** — with arithmetic, not a model's opinion.
>
> And the number you should push on is my hundred percent agreement: that's one reviewer, me,
> no adjudication, one catalog, who could see the gate's answers while judging. The harness
> prints those three caveats itself on every run.
>
> Thank you.

---

## Timing

| § | Surface | Measured |
|---|---|---|
| 0 · Open | site | 1:20 |
| 1 · Where each layer stops | site | 0:36 |
| 2 · How it decides | site | 0:43 |
| 3 · **Live run** | terminal | 2:27 talking |
| 3 · **the payment itself** | browser | ~0:30 |
| 4 · The numbers | site | 0:41 |
| 5 · The repo | github | 0:39 |
| 6 · Close | either | 0:26 |
| | | **7:30** including the payment |

Counted from the words at 160 a minute.

**Read this before you rehearse.** The opening has grown three times — the Razorpay stakes, the
definition, and the collision now all live in the first eighty seconds, and each was added for
a good reason. Together they put the run at 7:30, which is longer than almost any slot. **The
opening is now the strongest part and the most expensive part.** Decide the slot first, then
cut from the ladder below; do not try to trim live.

### Cut ladder

| Target | Drop | Lands at |
|---|---|---|
| **6:00** | §1's middle paragraph, and §5's second half | ~6:05 |
| **5:00** | …and §0's browser analogy *(keep it if the room is technical)*, and half of §3's narration | ~5:05 |
| **4:30** | …and the live payment — say *"I have one settled from earlier"* and show the finished chain | ~4:20 |

**Never cut:** §2, the confirm-refused moment in §3, and the self-criticism in §6. Those are the
differentiator, the part most builds skip, and the most credible thirty seconds you have.

## After — the questions

Press `/` in pitch mode, type a word: 28 anticipated questions with answers. `Esc` closes.

Rehearse this one out loud until it sounds like you mean it: *"Your corpus scores 100% —
isn't that suspicious?"* Agree instantly, produce the threshold peak underneath it, then give
the three bounds before they ask.

**If any screen dies:** `okayanshul.github.io/custodian` has every number and screenshot.
Keep talking.
