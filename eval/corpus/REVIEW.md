# Benign divergence — the reviewed labels

30 cases, judged by OkayAnshul. Nothing is awaiting review.

These are the labels that do not follow from how a case was built — whether one ingredient stands in acceptably for another is a judgment about cooking, and this file records the judgment that was made, next to the evidence it was made against.

The reasoning behind each call, including the rule that governs when a substitution may be rejected at all, is in `decisions.txt`. Re-running `python -m eval.corpus.review --apply --as NAME` overwrites these with a new reviewer's calls.

| case | asked → offered | policy | base | form | call | gate |
|---|---|---|---|---|---|---|
| `benign-001` | coconut milk → Coconut Cream 200 ml | `SAME_BASE` | 10000 | 8500 | **APPROVE** | APPROVE |
| `benign-002` | coconut cream → Dabur Coconut Milk 400ml | `SAME_BASE` | 10000 | 8500 | **APPROVE** | APPROVE |
| `benign-003` | coconut milk → Nariyal Powder 200 gm | `SAME_BASE` | 10000 | 6000 | **HOLD** | HOLD |
| `benign-004` | whole coriander → Dhania Powder 100gm | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-005` | coriander powder → Dhania Sabut 100g | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-006` | whole turmeric → Everest Haldi Powder 100gm | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-007` | mustard seeds → Mustard Oil / Sarson ka Tel 1 ltr | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-008` | sunflower oil → Groundnut Oil 1L | `EQUIVALENT` | 8000 | 10000 | **APPROVE** | APPROVE |
| `benign-009` | sunflower oil → Groundnut Oil 1L | `SAME_BASE` | 8000 | 10000 | **REJECT** | REJECT |
| `benign-010` | ghee → Amul Butter 100g | `EQUIVALENT` | 6500 | unlisted — escalates | **HOLD** | HOLD |
| `benign-011` | atta → maida 1kg | `EQUIVALENT` | 3000 | 10000 | **HOLD** | HOLD |
| `benign-012` | dahi → Amul Fresh Cream 200ml | `EQUIVALENT` | 4500 | unlisted — escalates | **HOLD** | HOLD |
| `benign-013` | desiccated coconut → Nariyal Powder 200 gm | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-014` | almond → Almond Milk 1 ltr Unsweetened | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-015` | chana dal → Moong Dal Dhuli 500 gm | `EQUIVALENT` | 3000 | 10000 | **HOLD** | HOLD |
| `benign-oos-001` | coconut milk → Coconut Cream 200 ml | `SAME_BASE` | 10000 | 8500 | **APPROVE** | APPROVE |
| `benign-oos-002` | coconut cream → Dabur Coconut Milk 400ml | `SAME_BASE` | 10000 | 8500 | **APPROVE** | APPROVE |
| `benign-oos-003` | coconut milk → Nariyal Powder 200 gm | `SAME_BASE` | 10000 | 6000 | **HOLD** | HOLD |
| `benign-oos-004` | whole coriander → Dhania Powder 100gm | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-oos-005` | coriander powder → Dhania Sabut 100g | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-oos-006` | whole turmeric → Everest Haldi Powder 100gm | `SAME_BASE` | 10000 | 7000 | **HOLD** | HOLD |
| `benign-oos-007` | mustard seeds → Mustard Oil / Sarson ka Tel 1 ltr | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-oos-008` | sunflower oil → Groundnut Oil 1L | `EQUIVALENT` | 8000 | 10000 | **APPROVE** | APPROVE |
| `benign-oos-009` | sunflower oil → Groundnut Oil 1L | `SAME_BASE` | 8000 | 10000 | **REJECT** | REJECT |
| `benign-oos-010` | ghee → Amul Butter 100g | `EQUIVALENT` | 6500 | unlisted — escalates | **HOLD** | HOLD |
| `benign-oos-011` | atta → maida 1kg | `EQUIVALENT` | 3000 | 10000 | **HOLD** | HOLD |
| `benign-oos-012` | dahi → Amul Fresh Cream 200ml | `EQUIVALENT` | 4500 | unlisted — escalates | **HOLD** | HOLD |
| `benign-oos-013` | desiccated coconut → Nariyal Powder 200 gm | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-oos-014` | almond → Almond Milk 1 ltr Unsweetened | `SAME_BASE` | 10000 | unlisted — escalates | **HOLD** | HOLD |
| `benign-oos-015` | chana dal → Moong Dal Dhuli 500 gm | `EQUIVALENT` | 3000 | 10000 | **HOLD** | HOLD |

The gate matches the reviewer on 30 of 30.

What that agreement is and is not: one reviewer, no adjudication, 15 distinct substitutions each applied to both variants of its pair — and the reviewer could see the gate's current call while judging, which makes agreement cheaper than an independent pass would be. `EVALUATION.md` states those bounds beside every number that rests on them.
