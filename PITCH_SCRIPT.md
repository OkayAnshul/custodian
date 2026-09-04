# The pitch — three surfaces, six minutes as written

**Read the `SAY` blocks aloud. Do the `DO` lines.** Every word is checked against the
repository, so you cannot overclaim by reading it.

The design principle: **each surface does only what it alone can do.**

| Surface | What it is for | Minutes |
|---|---|---|
| **pitch mode** (the site) | The argument — the collision, the gap, the numbers | 2:36 |
| **the terminal** (`make live`) | The proof — it runs, and real money moves | 2:24 |
| **GitHub** | The credibility — sixteen failures, green CI, a real repo | 0:39 |

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

# 0 · Open — 31s   `SITE`

**DO** — Tab 1, press `→` twice to **beat 2**. Start here, not at the beginning.
**POINT AT** — the big `0.3333` in the middle.

> Coconut milk is out of stock. An AI shopping agent offers you coconut cream — that's fine.
> It offers you almond milk — that's not.
>
> The obvious way to check that is text similarity. And text similarity scores those two
> **identically**. Point three three three, both. Same number, opposite answers.
>
> So this isn't a problem you solve by reading the agent's output more carefully. I'm Anshul,
> this is Custodian, and it decides whether an AI agent bought what the human actually asked
> for.

**Pause two seconds.**

---

# 1 · The gap, and whose problem it is — 38s   `SITE`

**DO** — press `←` twice to **beat 0**.
**POINT AT** — the empty **Purpose** row, then the red `SHIPPED · MARCH` tag.

> Four layers. Three are solved — MCP for talking to systems, ACP and UCP for building a
> cart, AP2 and UAP for proving the agent was **permitted** to spend. Every one of them stops
> before the question of *what* was bought. That's deliberate: a payment rail shouldn't
> adjudicate whether coconut cream is an acceptable substitute.
>
> Razorpay and Sarvam shipped a voice agent that pays without a PIN, Swiggy as launch
> partner, and stated that agentic shopping doesn't rewrite commercial liability. So when
> that agent orders wrong, **the merchant** eats it. That shipped in March.
>
> This checks **purpose alignment, not fraud.**

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

# 3 · Now watch it run — 1:54 of talking, plus the payment   `TERMINAL`  ← the proof

**DO** — switch to the terminal. Type it where they can see:

```bash
make live
```

Narrate over it. One line per stage — the script pauses for you.

> This is the merchant's actual export. Empty price column, stock spelled four ways, pack
> sizes living inside the product name.
>
> Seventy rows in, seventy items out, and it names every resolution it had to make. One item
> it *can't* place — that one escalates rather than guesses.
>
> Here's what the agent is allowed to see. Note it never gets the raw description — that's
> where injection lives.
>
> Now an untrusted agent builds a cart. It asserts ninety-nine rupees for an item the catalog
> prices at one ninety-nine, and it adds a fourteen-fifty wok nobody asked for.

**PAUSE — let the `REJECT` land.**

> Rejected. Not on a model's opinion — on arithmetic. It asserted eighteen ninety-three; the
> catalog says twenty ninety-three.
>
> And now watch a human try to confirm it anyway — **refused.** A constraint you can wave
> through is advisory. So the agent has to come back with a corrected cart.
>
> Price fixed. The wok is still there, and that's a judgment a human owns, so it **holds**
> rather than refusing. The human confirms *that* — and the record still reads hold, with a
> separate entry naming who overrode it. "Held, then a human said yes at 14:32" is the
> truthful entry, and it's the number a false-hold rate is measured from.
>
> Real Razorpay order. Two thousand and ninety-three rupees — **the derived total, not the
> claim.**

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

# 4 · What it's worth, and what it costs — 44s   `SITE`

**DO** — back to Tab 1, press `→` to **beat 5**.
**POINT AT** — the peak at 80%, and the fall-off on *both* sides.

> Across a hundred and twenty orders: thirty-one thousand six hundred rupees of purchases
> that didn't match intent, stopped or held — and **zero of sixty clean orders held.** The
> cost quoted in the same breath, because a saving without its cost is advertising.
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
> Five hundred and fifty-six tests, green.
>
> And this is the file I'd actually read first. Sixteen failures, written as they happened,
> with root causes. Fourteen of the sixteen were found by running the real thing rather than
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
| 0 · Open | site | 0:31 |
| 1 · The gap | site | 0:38 |
| 2 · How it decides | site | 0:43 |
| 3 · **Live run** | terminal | 1:54 talking |
| 3 · **the payment itself** | browser | ~0:30 |
| 4 · The numbers | site | 0:44 |
| 5 · The repo | github | 0:39 |
| 6 · Close | either | 0:26 |
| | | **6:05** including the payment |

These are counted from the words, at 160 a minute, not estimated. **You are over six minutes**
— so unless your slot is generous, take one of the cuts below before you record.

**To reach 5:00** — drop §5's middle paragraph and §1's middle paragraph, and cut §3's
narration to the five moments that matter: *the messy export · the forged cart · rejected ·
confirm refused · settled.* That removes about 170 words and lands near **5:00** with the
payment included.

**To reach 4:30** — also skip the live payment. Run `make live` up to the order, say *"and a
person pays on the hosted page — I have one settled from earlier"*, and show the finished
chain in the viewer. You keep every claim and lose only the pause.

**Never cut:** §2 (the differentiator), the confirm-refused moment in §3 (most builds demo the
block and stop), and the caveat in §6 (conceding first is worth more than any number).

---

## After — the questions

Press `/` in pitch mode, type a word: 28 anticipated questions with answers. `Esc` closes.

Rehearse this one out loud until it sounds like you mean it: *"Your corpus scores 100% —
isn't that suspicious?"* Agree instantly, produce the threshold peak underneath it, then give
the three bounds before they ask.

**If any screen dies:** `okayanshul.github.io/custodian` has every number and screenshot.
Keep talking.
