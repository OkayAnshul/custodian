"""What would have happened without Custodian, in money.

The gate's other numbers are rates — approval rate, catch rate, false-hold rate.
Rates are the right way to tune a threshold and the wrong way to explain the
system to someone deciding whether it is worth having. This answers the question
a merchant actually asks: *what does this save me, and what does it cost me?*

The counterfactual is not hypothetical. "Without Custodian" is a path this
repository already implements — `agent.buyer.NaiveBuyer` reading an unsanitised
feed and its asserted totals settling unchecked, which is exactly what happens
today when a merchant exposes a catalog to an AI buyer and nothing re-derives
the cart. So the comparison is between two runnable paths, not between a run and
an estimate.

Three quantities, kept separate because they are different claims:

**Wrong money stopped.** The catalog value of orders the gate did not approve.
Money that would have moved and should not have.

**Forged money stopped.** Where the agent's asserted price differs from the
catalog's, the difference. This is money that would have moved *at the wrong
amount* even on an order that was otherwise fine.

**Friction.** Clean orders sent back to a human. The cost side, reported in the
same breath, because a saving quoted without its cost is advertising.

    python -m eval.counterfactual
    python -m eval.counterfactual --split TEST
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custodian import bp
from custodian.gate.thresholds import DEFAULT
from custodian.ingest.snapshot import ingest_csv
from custodian.money import format_inr, line_total
from custodian.schemas.decision import Outcome
from eval.corpus.schema import CaseClass, Split
from eval.harness import CATALOG, MERCHANT, TAKEN_AT, build_input, load_corpus, run


@dataclass(frozen=True, slots=True)
class Counterfactual:
    """The two paths, side by side."""

    orders: int

    #: Everything the agent proposed, at the prices the agent asserted. This is
    #: what settles when nothing checks.
    unchecked_paise: int
    #: What Custodian let through, at catalog prices.
    settled_paise: int

    #: Catalog value of orders that were not approved.
    wrong_money_stopped_paise: int
    #: Value of the adversarial subset of that.
    adversarial_stopped_paise: int
    #: Sum of |asserted − catalog| across every line, on every order.
    forged_amount_paise: int
    #: Catalog value of cart lines that traced back to nothing requested. The
    #: ₹1,450 wok: correctly priced, in stock, inside budget, and not asked for.
    unrequested_paise: int

    clean_orders: int
    clean_orders_held: int
    orders_reaching_a_model: int

    #: Cart lines across the corpus, and the ones a deterministic check could
    #: not settle. Reported per line as well as per order because the cost of a
    #: model is charged per question asked, not per order placed.
    cart_lines: int
    lines_reaching_a_model: int

    @property
    def model_line_share_bp(self) -> int:
        return bp.from_ratio(self.lines_reaching_a_model, self.cart_lines) if self.cart_lines else 0

    @property
    def friction_bp(self) -> int:
        return bp.from_ratio(self.clean_orders_held, self.clean_orders) if self.clean_orders else 0

    @property
    def stopped_share_bp(self) -> int:
        total = self.settled_paise + self.wrong_money_stopped_paise
        return bp.from_ratio(self.wrong_money_stopped_paise, total) if total else 0


def measure(split: Split | None = None) -> Counterfactual:
    """Run both paths over the corpus and compare them in money."""
    corpus = load_corpus()
    base, _ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    results = run(corpus, split=split)

    unchecked = settled = wrong = adversarial = forged = unrequested = 0
    clean = clean_held = escalating = 0
    cart_lines = escalating_lines = 0

    for result in results:
        # Rebuild the exact input the gate saw, so every figure below comes from
        # the same objects the decision was made from rather than a second
        # reading of the case file that could drift from it.
        inp = build_input(result.case, base, DEFAULT)
        asserted = inp.cart.asserted_total_paise
        verified = result.decision.verified_total_paise

        unchecked += asserted
        forged += abs(verified - asserted)
        cart_lines += len(inp.cart.lines)
        escalating_lines += len(result.escalated)

        if result.decision.outcome is Outcome.APPROVE:
            settled += verified
        else:
            wrong += verified
            if result.case.case_class is CaseClass.ADVERSARIAL:
                adversarial += verified

        # Value of lines that trace back to nothing anyone asked for.
        unbound = {b.cart_line_id for b in result.decision.bindings
                   if b.requested_line_id is None}
        for line in inp.cart.lines:
            if line.line_id in unbound:
                item = inp.snapshot.find(line.item_id)
                if item is not None:
                    unrequested += line_total(item.price_paise, line.quantity)

        if result.case.case_class is CaseClass.CLEAN:
            clean += 1
            clean_held += result.decision.outcome is not Outcome.APPROVE
        escalating += bool(result.escalated)

    return Counterfactual(
        orders=len(results),
        unchecked_paise=unchecked,
        settled_paise=settled,
        wrong_money_stopped_paise=wrong,
        adversarial_stopped_paise=adversarial,
        forged_amount_paise=forged,
        unrequested_paise=unrequested,
        clean_orders=clean,
        clean_orders_held=clean_held,
        orders_reaching_a_model=escalating,
        cart_lines=cart_lines,
        lines_reaching_a_model=escalating_lines,
    )


def report(measured: Counterfactual, *, split: str) -> None:
    m = measured
    print(f"\nWithout Custodian — {split} split, {m.orders} orders")
    print("─" * 78)
    print(f"  {'money that would settle unchecked':<42} {format_inr(m.unchecked_paise):>14}")
    print(f"  {'money Custodian let through':<42} {format_inr(m.settled_paise):>14}")
    print(f"  {'money stopped or held for a human':<42} {format_inr(m.wrong_money_stopped_paise):>14}"
          f"   {bp.to_str(m.stopped_share_bp)} of value")
    print()
    print(f"  {'of that, adversarial orders':<42} {format_inr(m.adversarial_stopped_paise):>14}")
    print(f"  {'price forged by the agent':<42} {format_inr(m.forged_amount_paise):>14}"
          f"   would have charged the wrong amount")
    print(f"  {'items nobody asked for':<42} {format_inr(m.unrequested_paise):>14}"
          f"   inside budget, correctly priced")
    print()
    print(f"  {'clean orders sent back to a human':<42} {m.clean_orders_held:>3} of {m.clean_orders:<9}"
          f"  {bp.to_str(m.friction_bp)} friction")
    print(f"  {'orders that needed a model at all':<42} {m.orders_reaching_a_model:>3} of {m.orders}")
    print(f"  {'cart lines that needed a model at all':<42} {m.lines_reaching_a_model:>3} of {m.cart_lines:<9}"
          f"  {bp.to_str(m.model_line_share_bp)} of lines")
    print()
    print(f"  Across {m.orders} orders, {format_inr(m.wrong_money_stopped_paise)} of purchases that did")
    print(f"  not match intent were stopped or held, at {bp.to_str(m.friction_bp)} friction on "
          f"{m.clean_orders} clean orders.")


def transactability() -> dict[str, int]:
    """How much of the raw export an agent could act on, before and after ingest.

    "Act on" is defined narrowly and each criterion is reported separately, so
    the claim can be checked rather than taken: a buying agent needs a price it
    can read, an identity it can match against a request, and a stock signal it
    can evaluate. A row missing any of the three cannot be bought from reliably.

    The raw column is the honest baseline — it is what a merchant exposing their
    export to an AI buyer today would actually be handing over.
    """
    import csv

    from custodian.money import MoneyError, parse_paise

    unambiguous_stock = {"yes", "no", "true", "false"}
    rows = list(csv.DictReader(CATALOG.open(encoding="utf-8")))

    def priced(row) -> bool:
        try:
            return parse_paise((row.get("price") or "").strip()) > 0
        except MoneyError:
            return False

    raw_priced = sum(priced(r) for r in rows)
    raw_categorised = sum(bool((r.get("category") or "").strip()) for r in rows)
    raw_stock = sum((r.get("stock") or "").strip().lower() in unambiguous_stock for r in rows)
    raw_sized = 0  # pack size is never its own column; it lives inside the name
    raw_all = sum(
        priced(r) and bool((r.get("category") or "").strip())
        and (r.get("stock") or "").strip().lower() in unambiguous_stock
        for r in rows
    )

    snapshot, report_ = ingest_csv(CATALOG, merchant_id=MERCHANT, taken_at=TAKEN_AT)
    placed = sum(1 for item in snapshot.items if item.resolved)
    sized = sum(1 for item in snapshot.items if item.unit is not None)

    return {
        "rows": len(rows),
        "raw_priced": raw_priced, "raw_categorised": raw_categorised,
        "raw_stock": raw_stock, "raw_sized": raw_sized, "raw_all": raw_all,
        "ingested": report_.items_built, "placed": placed, "sized": sized,
    }


def report_transactability(t: dict[str, int]) -> None:
    n = t["rows"]
    print(f"\nThe transactability half — {n} rows of a real kirana export")
    print("─" * 78)
    print(f"  {'':34} {'raw':>10} {'after ingest':>14}")
    print(f"  {'price an agent can read':<34} {t['raw_priced']:>7} /{n:<3} {t['ingested']:>10} /{n}")
    print(f"  {'identity it can match a request to':<34} {t['raw_categorised']:>7} /{n:<3} "
          f"{t['placed']:>10} /{n}")
    print(f"  {'stock signal without a lookup table':<34} {t['raw_stock']:>7} /{n:<3} "
          f"{t['ingested']:>10} /{n}")
    print(f"  {'canonical pack size':<34} {t['raw_sized']:>7} /{n:<3} {t['sized']:>10} /{n}")
    print(f"  {'':34} {'───':>10} {'───':>14}")
    print(f"  {'ALL THREE — actually buyable from':<34} {t['raw_all']:>7} /{n:<3} "
          f"{min(t['placed'], t['ingested']):>10} /{n}")
    print()
    print(f"  A merchant with unusable product data is invisible to agents however good")
    print(f"  the checkout is. That is the growth half, and it is measurable.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["DEV", "TEST", "ALL"], default="ALL")
    args = parser.parse_args()
    split = None if args.split == "ALL" else Split(args.split)
    report_transactability(transactability())
    report(measure(split), split=args.split)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
