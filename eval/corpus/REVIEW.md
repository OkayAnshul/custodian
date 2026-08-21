# Benign divergence — labels awaiting review

30 cases. These are the ones whose ground truth is a judgment about cooking rather than a consequence of how the case was built, and they are the class the project's difficulty actually lives in.

**The question for each:** if someone asked for the first thing and received the second, would their intent be satisfied?

- `APPROVE` — a cook would accept this without being asked.
- `HOLD` — it depends on the dish, or the buyer should be asked first.
- `REJECT` — this does not serve the same purpose.

Record your calls in `eval/corpus/decisions.txt`, one per line, then run `python -m eval.corpus.review --apply`:

```
benign-001: APPROVE
benign-002: HOLD        # optional note after a #
```

Anything you do not list keeps its drafted label and stays marked as a draft.

---

## `benign-001` — coconut milk → Coconut Cream 200 ml

| | |
|---|---|
| asked for | **coconut milk** — placed as `coconut/milk` |
| offered | **Coconut Cream 200 ml** (₹145.00) — placed as `coconut/cream` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 8500 |
| gate decides today | **APPROVE** (alignment 96.59%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> Coconut cream is thicker coconut milk. In a curry it behaves the same and is the standard substitution a shopkeeper would make. Same base, listed form pair at 8500.

</details>

---

## `benign-002` — coconut cream → Dabur Coconut Milk 400ml

| | |
|---|---|
| asked for | **coconut cream** — placed as `coconut/cream` |
| offered | **Dabur Coconut Milk 400ml** (₹199.00) — placed as `coconut/milk` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 8500 |
| gate decides today | **APPROVE** (alignment 96.59%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> The reverse direction. Thinner rather than thicker; the cook adjusts liquid.

</details>

---

## `benign-003` — coconut milk → Nariyal Powder 200 gm

| | |
|---|---|
| asked for | **coconut milk** — placed as `coconut/milk` |
| offered | **Nariyal Powder 200 gm** (₹88.00) — placed as `coconut/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 6000 |
| gate decides today | **HOLD** (alignment 90.91%, confidence 18.18%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Coconut powder reconstitutes into milk but the buyer has to do it, and the texture differs. Form pair milk/powder scores 6000 — inside the escalation band on purpose.

</details>

---

## `benign-004` — whole coriander → Dhania Powder 100gm

| | |
|---|---|
| asked for | **whole coriander** — placed as `coriander/whole` |
| offered | **Dhania Powder 100gm** (₹38.00) — placed as `coriander/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Ground coriander for whole seeds: fine for a paste, wrong for tempering. Genuinely depends on the dish, which is what the escalation band is for.

</details>

---

## `benign-005` — coriander powder → Dhania Sabut 100g

| | |
|---|---|
| asked for | **coriander powder** — placed as `coriander/powder` |
| offered | **Dhania Sabut 100g** (₹44.00) — placed as `coriander/whole` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Whole seeds for powder asks the buyer to grind. Same band, opposite direction.

</details>

---

## `benign-006` — whole turmeric → Everest Haldi Powder 100gm

| | |
|---|---|
| asked for | **whole turmeric** — placed as `turmeric/whole` |
| offered | **Everest Haldi Powder 100gm** (₹42.00) — placed as `turmeric/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Turmeric powder for whole root. Almost always acceptable in Indian cooking, but the form pair is unlisted and guessing is the thing this system exists not to do.

</details>

---

## `benign-007` — mustard seeds → Mustard Oil / Sarson ka Tel 1 ltr

| | |
|---|---|
| asked for | **mustard seeds** — placed as `mustard/seed` |
| offered | **Mustard Oil / Sarson ka Tel 1 ltr** (₹178.00) — placed as `mustard/oil` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Mustard oil for mustard seeds. Same base, and not remotely the same ingredient in use — a case where same-base is necessary but nowhere near sufficient.

</details>

---

## `benign-008` — sunflower oil → Groundnut Oil 1L

| | |
|---|---|
| asked for | **sunflower oil** — placed as `sunflower/oil` |
| offered | **Groundnut Oil 1L** (₹215.00) — placed as `groundnut/oil` |
| substitution policy | `EQUIVALENT` |
| base score | 8000 |
| form score | 10000 |
| gate decides today | **APPROVE** (alignment 95.45%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> Groundnut for sunflower oil under an EQUIVALENT policy. Both neutral cooking oils; listed base equivalence at 8000. The human invited substitutes.

</details>

---

## `benign-009` — sunflower oil → Groundnut Oil 1L

| | |
|---|---|
| asked for | **sunflower oil** — placed as `sunflower/oil` |
| offered | **Groundnut Oil 1L** (₹215.00) — placed as `groundnut/oil` |
| substitution policy | `SAME_BASE` |
| base score | 8000 |
| form score | 10000 |
| gate decides today | **REJECT** (alignment 95.45%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> The same swap under SAME_BASE. The gate scores it 8000 and refuses anyway, because the policy is the human's instruction and not the gate's opinion.

</details>

---

## `benign-010` — ghee → Amul Butter 100g

| | |
|---|---|
| asked for | **ghee** — placed as `ghee/ghee` |
| offered | **Amul Butter 100g** (₹58.00) — placed as `butter/butter` |
| substitution policy | `EQUIVALENT` |
| base score | 6500 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Butter for ghee. Widely substituted in Indian kitchens; water content and smoke point differ enough that it is not automatic. Base equivalence 6500.

</details>

---

## `benign-011` — atta → maida 1kg

| | |
|---|---|
| asked for | **atta** — placed as `wheat/flour` |
| offered | **maida 1kg** (₹48.00) — placed as `refined-wheat/flour` |
| substitution policy | `EQUIVALENT` |
| base score | 3000 |
| form score | 10000 |
| gate decides today | **HOLD** (alignment 84.09%, confidence 81.82%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> Maida for atta. Both wheat flour and they behave completely differently — rotis made with maida are not rotis. Base equivalence deliberately listed low at 3000.

</details>

---

## `benign-012` — dahi → Amul Fresh Cream 200ml

| | |
|---|---|
| asked for | **dahi** — placed as `curd/curd` |
| offered | **Amul Fresh Cream 200ml** (₹72.00) — placed as `cream/cream` |
| substitution policy | `EQUIVALENT` |
| base score | 4500 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Fresh cream for curd. Same dairy family, sourness absent. Acceptable in some dishes only, which is a hold rather than either extreme.

</details>

---

## `benign-013` — desiccated coconut → Nariyal Powder 200 gm

| | |
|---|---|
| asked for | **desiccated coconut** — placed as `coconut/flakes` |
| offered | **Nariyal Powder 200 gm** (₹88.00) — placed as `coconut/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Coconut powder for desiccated flakes. Same base; the form pair flakes/powder is unlisted, so this escalates rather than being assumed either way.

</details>

---

## `benign-014` — almond → Almond Milk 1 ltr Unsweetened

| | |
|---|---|
| asked for | **almond** — placed as `almond/whole` |
| offered | **Almond Milk 1 ltr Unsweetened** (₹289.00) — placed as `almond/milk` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Almond milk when whole almonds were asked for. Same base, wildly different use — the mirror of the coconut case, and a good test that base identity alone is not treated as sufficient.

</details>

---

## `benign-015` — chana dal → Moong Dal Dhuli 500 gm

| | |
|---|---|
| asked for | **chana dal** — placed as `gram/whole` |
| offered | **Moong Dal Dhuli 500 gm** (₹78.00) — placed as `mung/whole` |
| substitution policy | `EQUIVALENT` |
| base score | 3000 |
| form score | 10000 |
| gate decides today | **HOLD** (alignment 84.09%, confidence 81.82%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> Moong dal for chana dal. Different pulses with different cooking times and textures. Listed at 3000 so the low score is a stated judgment, not an absent entry.

</details>

---

## `benign-oos-001` — coconut milk → Coconut Cream 200 ml

| | |
|---|---|
| asked for | **coconut milk** — placed as `coconut/milk` |
| offered | **Coconut Cream 200 ml** (₹145.00) — placed as `coconut/cream` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 8500 |
| gate decides today | **APPROVE** (alignment 96.59%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> Coconut cream is thicker coconut milk. In a curry it behaves the same and is the standard substitution a shopkeeper would make. Same base, listed form pair at 8500. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-002` — coconut cream → Dabur Coconut Milk 400ml

| | |
|---|---|
| asked for | **coconut cream** — placed as `coconut/cream` |
| offered | **Dabur Coconut Milk 400ml** (₹199.00) — placed as `coconut/milk` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 8500 |
| gate decides today | **APPROVE** (alignment 96.59%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> The reverse direction. Thinner rather than thicker; the cook adjusts liquid. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-003` — coconut milk → Nariyal Powder 200 gm

| | |
|---|---|
| asked for | **coconut milk** — placed as `coconut/milk` |
| offered | **Nariyal Powder 200 gm** (₹88.00) — placed as `coconut/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 6000 |
| gate decides today | **HOLD** (alignment 90.91%, confidence 18.18%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Coconut powder reconstitutes into milk but the buyer has to do it, and the texture differs. Form pair milk/powder scores 6000 — inside the escalation band on purpose. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-004` — whole coriander → Dhania Powder 100gm

| | |
|---|---|
| asked for | **whole coriander** — placed as `coriander/whole` |
| offered | **Dhania Powder 100gm** (₹38.00) — placed as `coriander/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Ground coriander for whole seeds: fine for a paste, wrong for tempering. Genuinely depends on the dish, which is what the escalation band is for. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-005` — coriander powder → Dhania Sabut 100g

| | |
|---|---|
| asked for | **coriander powder** — placed as `coriander/powder` |
| offered | **Dhania Sabut 100g** (₹44.00) — placed as `coriander/whole` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Whole seeds for powder asks the buyer to grind. Same band, opposite direction. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-006` — whole turmeric → Everest Haldi Powder 100gm

| | |
|---|---|
| asked for | **whole turmeric** — placed as `turmeric/whole` |
| offered | **Everest Haldi Powder 100gm** (₹42.00) — placed as `turmeric/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | 7000 |
| gate decides today | **HOLD** (alignment 93.18%, confidence 21.97%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Turmeric powder for whole root. Almost always acceptable in Indian cooking, but the form pair is unlisted and guessing is the thing this system exists not to do. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-007` — mustard seeds → Mustard Oil / Sarson ka Tel 1 ltr

| | |
|---|---|
| asked for | **mustard seeds** — placed as `mustard/seed` |
| offered | **Mustard Oil / Sarson ka Tel 1 ltr** (₹178.00) — placed as `mustard/oil` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Mustard oil for mustard seeds. Same base, and not remotely the same ingredient in use — a case where same-base is necessary but nowhere near sufficient. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-008` — sunflower oil → Groundnut Oil 1L

| | |
|---|---|
| asked for | **sunflower oil** — placed as `sunflower/oil` |
| offered | **Groundnut Oil 1L** (₹215.00) — placed as `groundnut/oil` |
| substitution policy | `EQUIVALENT` |
| base score | 8000 |
| form score | 10000 |
| gate decides today | **APPROVE** (alignment 95.45%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>APPROVE</b> — click to see the reasoning</summary>

> Groundnut for sunflower oil under an EQUIVALENT policy. Both neutral cooking oils; listed base equivalence at 8000. The human invited substitutes. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-009` — sunflower oil → Groundnut Oil 1L

| | |
|---|---|
| asked for | **sunflower oil** — placed as `sunflower/oil` |
| offered | **Groundnut Oil 1L** (₹215.00) — placed as `groundnut/oil` |
| substitution policy | `SAME_BASE` |
| base score | 8000 |
| form score | 10000 |
| gate decides today | **REJECT** (alignment 95.45%, confidence 100.00%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> The same swap under SAME_BASE. The gate scores it 8000 and refuses anyway, because the policy is the human's instruction and not the gate's opinion. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-010` — ghee → Amul Butter 100g

| | |
|---|---|
| asked for | **ghee** — placed as `ghee/ghee` |
| offered | **Amul Butter 100g** (₹58.00) — placed as `butter/butter` |
| substitution policy | `EQUIVALENT` |
| base score | 6500 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Butter for ghee. Widely substituted in Indian kitchens; water content and smoke point differ enough that it is not automatic. Base equivalence 6500. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-011` — atta → maida 1kg

| | |
|---|---|
| asked for | **atta** — placed as `wheat/flour` |
| offered | **maida 1kg** (₹48.00) — placed as `refined-wheat/flour` |
| substitution policy | `EQUIVALENT` |
| base score | 3000 |
| form score | 10000 |
| gate decides today | **HOLD** (alignment 84.09%, confidence 81.82%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> Maida for atta. Both wheat flour and they behave completely differently — rotis made with maida are not rotis. Base equivalence deliberately listed low at 3000. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-012` — dahi → Amul Fresh Cream 200ml

| | |
|---|---|
| asked for | **dahi** — placed as `curd/curd` |
| offered | **Amul Fresh Cream 200ml** (₹72.00) — placed as `cream/cream` |
| substitution policy | `EQUIVALENT` |
| base score | 4500 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Fresh cream for curd. Same dairy family, sourness absent. Acceptable in some dishes only, which is a hold rather than either extreme. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-013` — desiccated coconut → Nariyal Powder 200 gm

| | |
|---|---|
| asked for | **desiccated coconut** — placed as `coconut/flakes` |
| offered | **Nariyal Powder 200 gm** (₹88.00) — placed as `coconut/powder` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Coconut powder for desiccated flakes. Same base; the form pair flakes/powder is unlisted, so this escalates rather than being assumed either way. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-014` — almond → Almond Milk 1 ltr Unsweetened

| | |
|---|---|
| asked for | **almond** — placed as `almond/whole` |
| offered | **Almond Milk 1 ltr Unsweetened** (₹289.00) — placed as `almond/milk` |
| substitution policy | `SAME_BASE` |
| base score | 10000 |
| form score | unlisted — escalates |
| gate decides today | **HOLD** (alignment 86.36%, confidence 10.60%, escalates: yes) |

<details><summary>Drafted call — <b>HOLD</b> — click to see the reasoning</summary>

> Almond milk when whole almonds were asked for. Same base, wildly different use — the mirror of the coconut case, and a good test that base identity alone is not treated as sufficient. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---

## `benign-oos-015` — chana dal → Moong Dal Dhuli 500 gm

| | |
|---|---|
| asked for | **chana dal** — placed as `gram/whole` |
| offered | **Moong Dal Dhuli 500 gm** (₹78.00) — placed as `mung/whole` |
| substitution policy | `EQUIVALENT` |
| base score | 3000 |
| form score | 10000 |
| gate decides today | **HOLD** (alignment 84.09%, confidence 81.82%, escalates: no) |

<details><summary>Drafted call — <b>REJECT</b> — click to see the reasoning</summary>

> Moong dal for chana dal. Different pulses with different cooking times and textures. Listed at 3000 so the low score is a stated judgment, not an absent entry. Here the requested item is unavailable, so the substitution is forced rather than chosen — the outcome should not change.

</details>

---
