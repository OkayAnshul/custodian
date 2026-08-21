# Defending this

Notes for the panel round. Not answers to memorise — the reasoning underneath them, so an unexpected question is answerable from first principles rather than from recall.

The rule for all of it: **when you don't know, say so and say what would settle it.** This project's entire thesis is that a system which knows it doesn't know beats one that's confidently wrong. Performing certainty you don't have contradicts the thing you're presenting.

---

## The five questions that decide the room

### "Isn't this just an LLM guardrail?"

The one that kills the submission if answered vaguely. Don't argue the category — show the mechanism.

> "A guardrail reads text and forms an opinion about it. Custodian doesn't read the agent's output — it re-derives the answer independently from a catalog it controls and a mandate with hard numbers, and compares. When the agent says a tin of coconut milk costs ₹99, nothing inspects that claim for plausibility; it's looked up and it's ₹199, so the order is rejected on arithmetic.
>
> Measured: fifteen percent of cart lines reach a model. Zero adversarial cases do."

If pressed on where a model *is* used: two places, both deliberate, and §6 of the README lists what was kept out and why.

### "Why is the LLM there at all?"

> "Two places. Turning 'ingredients for a Thai curry, under ₹2,000' into structured constraints — that's genuinely language and nothing else does it. And breaking ties on form pairs nobody has judged: turmeric whole for turmeric powder is almost always fine and I don't have a table entry for it, so rather than guess, it asks.
>
> The second one sees the cooking context and two item descriptors. No price, no budget, no mandate, no total. It's not deciding whether a purchase should proceed and it can't see what that would require."

**The follow-up to be ready for:** *"So a compromised model can't approve a bad order?"* — It can raise one dimension's score inside the escalation band. It can't raise it past a failed dimension elsewhere, because any `FAIL` or `UNCERTAIN` caps the outcome at `HOLD` regardless of score. And it never sees a cart the arithmetic already settled.

### "Your corpus scores 100%. Isn't that suspicious?"

Agree with them. It's the strongest move available and it happens to be true.

> "Yes, and the harness says so in its own output. Three of the four classes have labels that follow from how each case was built — a forged price is a rejection by construction. Scoring 100% says the implementation matches its specification. It doesn't say the specification is right.
>
> The class where that question actually lives is benign divergence, and those thirty labels are drafts. I won't quote a number resting on labels a model drafted, because that's measuring its own consistency."

**If the labels are reviewed by then**, this becomes the strongest answer in the deck instead of an honest gap. Worth doing before the round.

### "What happens when it doesn't know?"

> "It holds, and holding is a real outcome rather than a soft reject. Confidence is computed from two things: how much of the cart's value was settled by arithmetic rather than by a model, and how far the score sits from the nearest threshold. A cart at 8001 against an 8000 threshold is arithmetically an approval and practically a coin flip, and saying so is the difference between calibrated and confident.
>
> It is never the model's self-reported confidence. That number tracks fluency, not accuracy."

### "What did you deliberately not build?"

> "Most obvious ideas in this track are a worse version of something Razorpay shipped last quarter — retry routing is Optimizer, chargeback evidence is the Dispute Auto-Responder, mandate caps are Reserve Pay. Custodian consumes the mandate as an input and emits what the dispute responder would need.
>
> And no vector store, no RAG, no agent framework. Reaching for LangChain here would actively cost points on AI judgment — the deterministic core is the argument, and adding a retrieval layer to a problem solved by a dictionary lookup would be the opposite of the point."

---

## Per-subsystem

For each: the thirty-second version, why it's built that way, and where it breaks.

### The taxonomy — the one component that isn't plumbing

**30s.** Every product, in the catalog and in the request, reduces to `(base, form, category)` against a hand-authored lexicon. Substitution scores identity first, then shape.

**Why not lexical similarity.** Because it can't decide the flagship case. `jaccard("coconut milk","coconut cream")` and `jaccard("coconut milk","almond milk")` are both 0.3333 — identical scores, opposite ground truth. There's a test asserting that, so the premise is checkable rather than argued.

**Why the weakest attribute governs.** Two scores combine by minimum, not average. Averaging lets a perfect base identity carry an incompatible form past the threshold.

**Where it breaks.** Coverage. 56 bases sized to one 70-item catalog; 69 of 70 place. A different merchant's catalog is unmeasured, and scaling it is authoring work rather than engineering work. That's the honest shape of the problem and it's also why it's hard to copy.

**In production.** The lexicon becomes a merchant-editable artifact with its own review workflow, and unplaced items become a queue rather than a permanent escalation.

### The gate

**30s.** Deterministic checks run first and reject on their own authority. Only survivors reach binding and substitution scoring. Only genuine ties reach a model. Eight dimensions, scored separately, each with reason codes.

**The invariant worth naming.** `decide()` is pure — no clock, no network, no randomness, no dict-order dependence. Staleness is a comparison between two *recorded* timestamps, never a clock read, which is what keeps it replayable.

**The bug worth volunteering.** `BROKE.md` 007: it approved an order with a failed dimension. Substitution scored 34%, seven passing dimensions carried the weighted mean to 85%, and it approved. I'd written "a constraint that can be outvoted by a good average is not a constraint" as a comment inside that exact function.

Fixed structurally rather than by re-tuning weights: any `FAIL` or `UNCERTAIN` caps the outcome at `HOLD`. **Weights decide how much a dimension contributes; they don't decide whether a failure counts.** A blocking-code list depends on someone registering each new code; a status rule covers dimensions that don't exist yet.

*Volunteering this is a strength.* It shows the failure mode was found, understood, and fixed at the right level.

### The ledger

**30s.** Append-only, hash-chained, on SQLite. Every payload separates `observed` — a catalog price, a gateway response, the JSON a model returned — from `inferred`, what was concluded from it.

**Why hash a structure, not a concatenation.** `event_type="AB", event_id="C"` and `event_type="A", event_id="BC"` produce identical bytes under concatenation and therefore identical hashes.

**Why triggers *and* a hash chain.** Triggers stop the likely case — a helper written under time pressure that "fixes up" a row. An attacker drops the triggers first, which is why the tamper tests **defeat the triggers deliberately** and then assert the chain still catches the edit.

**Where it breaks.** Tamper-*evidence*, not tamper-proofing. Someone who can rewrite the whole chain and every artifact leaves a self-consistent record. External anchoring of the head is the fix and isn't built.

### Replay

**30s.** Take a ledger entry, load the inputs it names, run the same pure function, compare bytes. The model client is mocked to raise if called, so "replayable without a model" is enforced rather than asserted.

**The apparent contradiction, and the resolution.** A judge will spot that the model participates in decisions yet decisions replay without one. The model runs *upstream*; its verdict is recorded as an **observation**, with the same standing as a catalog price. Replay reads what it said rather than re-asking.

**The detail worth mentioning.** Replay refuses outright when the lexicon version differs from the recorded one, rather than quietly producing a different answer. The tables are an input, so a different lexicon is a different decision.

### Payments

**30s.** Behind a four-method Protocol. The fake and the real Razorpay client pass one contract suite; twelve of those tests run against the live test-mode API.

**The bug worth volunteering.** `BROKE.md` 006. The Protocol had `create_order` then `capture(order)`. Razorpay is `order → a human pays → authorized payment → capture`. An unpaid order has zero payments and nothing to capture. `FakeGateway` passed the whole contract, through every phase up to that point, against an API I had *imagined*.

**The lesson to state.** A fake that satisfies a contract the real thing can't is worse than no fake — it converts an unknown into false confidence. The spike was scheduled first precisely because this was the riskiest unknown, and it stayed unknown until real credentials forced the question, because a green suite felt like evidence.

**Two controls against double payment, because there are two failure modes.** An idempotency key protects a retry. It does nothing against an untrusted client generating a fresh key — so capture also refuses an order already paid. A control an agent walks around by changing one string isn't a control.

### The evaluation

**30s.** 120 cases, four classes, DEV/TEST split, stratified. Thresholds chosen on DEV, numbers reported on TEST.

**The design decision to lead with.** Label provenance is a typed field. `Case` *refuses to construct* a benign-divergence case with a derived label — the integrity constraint is enforced, not remembered.

**The sweep finding worth stating.** The adversarial catch rate doesn't move across any dial. Every attack in this corpus is settled deterministically, so tightening a threshold spends friction and buys no safety. That's worth knowing before anyone turns it up hoping for protection it can't provide.

**Where it's weak.** 30 drafted labels; single merchant; adversarial cases are ones I thought of.

---

## Two questions with no comfortable answer

Prepare these properly. Fumbling an honest limitation costs more than the limitation does.

### "Is the mandate real?"

> "No, and the README says so in the limitations. Reserve Pay isn't reachable from a self-serve test account, so the mandate is constructed locally and checked deterministically. The order creation, the payable link, the fetch and the capture are live Razorpay test-mode calls and the payment ids in the ledger are Razorpay's — but the mandate envelope is modelled.
>
> What this demonstrates is the layer *above* the mandate. It consumes one as an input, which is what makes it complementary to Reserve Pay rather than a worse version of it."

Do **not** blur this. A judge who discovers a modelled integration described as real stops believing everything else.

### "You built this with an AI. What did you actually do?"

Answer with the specific decisions, not a disclaimer.

> "The architecture arguments are the work. Attribute decomposition instead of the lexical primitive I'd originally specified, because I worked the flagship example by hand and found the primitive couldn't decide it. Splitting base equivalence from form compatibility, because one table conflating them would let a form rule authorise an identity change. Keeping the model's output as a recorded observation so decisions replay without it.
>
> And the lexicon and the corpus are judgment — 56 bases, 24 form pairs, 120 cases each with a written rationale. The thirty labels that need cooking judgment are the ones I won't let a model supply, and `BROKE.md` 010 is me catching myself putting three fabricated ones in during a test."

---

## What to have open

| | |
|---|---|
| `BROKE.md` | Entries 006, 007, 009, 010. Ten failures with root causes is the strongest single artifact here |
| `README.md` §5 | The table of where a model was deliberately not used |
| The viewer | `make serve`, then `/view/…` — the per-dimension breakdown lands faster than any explanation |
| `EVALUATION.md` | For the corpus question, which will come |

## If you get one sentence

> "Everything in the stack proves the agent was allowed to spend. Custodian is the first thing that checks it bought the right thing — and it does that with arithmetic, not with a model's opinion."
