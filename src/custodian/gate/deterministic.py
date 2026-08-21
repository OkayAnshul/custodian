"""The checks that reject on their own authority.

Everything here is decidable by arithmetic, equality, or set membership, so
nothing here consults a model. These run first, and the semantic scorer never
sees a case they have already settled — which is both a cost argument and a
correctness one: a model asked whether ₹199 equals ₹199 can be wrong.

Each check returns a ``DimensionResult`` rather than a boolean. A gate that
answers "no" without saying which of six things failed is not one a merchant can
act on, and the reason codes are what the eval harness asserts against.
"""

from __future__ import annotations

from custodian.clock import seconds_between
from custodian.gate.reasons import ReasonCode
from custodian.gate.thresholds import Thresholds
from custodian.money import line_total
from custodian.schemas.cart import Cart
from custodian.schemas.catalog import UNKNOWN, CatalogSnapshot
from custodian.schemas.decision import Dimension, DimensionResult, DimensionStatus
from custodian.schemas.intent import Intent
from custodian.schemas.mandate import Mandate

FULL = 10_000


def _result(dimension: Dimension, codes: list[ReasonCode], *, ok: bool, score: int | None = None):
    return DimensionResult(
        dimension=dimension,
        status=DimensionStatus.PASS if ok else DimensionStatus.FAIL,
        score_bp=FULL if score is None and ok else (score or 0),
        reason_codes=tuple(codes),
    )


def verified_total_paise(cart: Cart, snapshot: CatalogSnapshot) -> int:
    """The gate's own arithmetic over catalog prices.

    This is the amount that may be charged. The agent's asserted total is a
    claim recorded beside it and is never what settles.
    """
    total = 0
    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is not None:
            total += line_total(item.price_paise, line.quantity)
    return total


def check_price_integrity(
    cart: Cart, snapshot: CatalogSnapshot, *, evaluated_at: str, thresholds: Thresholds
) -> DimensionResult:
    """Is the price the catalog price, or the price the agent asserts?"""
    codes: list[ReasonCode] = []

    age = seconds_between(snapshot.taken_at, evaluated_at)
    if age > thresholds.max_snapshot_age_seconds:
        codes.append(ReasonCode.SNAPSHOT_STALE)

    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is None:
            codes.append(ReasonCode.ITEM_NOT_IN_CATALOG)
            continue
        if not item.in_stock:
            codes.append(ReasonCode.ITEM_OUT_OF_STOCK)
        if abs(item.price_paise - line.asserted_unit_price_paise) > thresholds.price_tolerance_paise:
            codes.append(ReasonCode.PRICE_MISMATCH)

    if codes:
        return _result(Dimension.PRICE_INTEGRITY, _dedupe(codes), ok=False)
    return _result(Dimension.PRICE_INTEGRITY, [ReasonCode.PRICE_MATCHES_CATALOG], ok=True)


def check_budget(
    intent: Intent, cart: Cart, snapshot: CatalogSnapshot, *, verified_total: int
) -> DimensionResult:
    """Does the re-derived total fit inside what the human authorised?"""
    codes: list[ReasonCode] = []

    for line in cart.lines:
        item = snapshot.find(line.item_id)
        requested = intent.find(line.satisfies_line_id or "")
        ceiling = requested.max_unit_price_paise if requested else None
        if item is not None and ceiling is not None and item.price_paise > ceiling:
            codes.append(ReasonCode.UNIT_PRICE_CEILING_EXCEEDED)

    if intent.budget_paise is None:
        codes.append(ReasonCode.BUDGET_UNSET)
        return _result(Dimension.BUDGET, _dedupe(codes), ok=not codes[:-1], score=FULL)

    if verified_total > intent.budget_paise:
        codes.append(ReasonCode.BUDGET_EXCEEDED)
        return _result(Dimension.BUDGET, _dedupe(codes), ok=False)

    if codes:
        return _result(Dimension.BUDGET, _dedupe(codes), ok=False)
    return _result(Dimension.BUDGET, [ReasonCode.BUDGET_SATISFIED], ok=True)


def check_merchant_scope(intent: Intent, cart: Cart, mandate: Mandate) -> DimensionResult:
    """Is this a merchant the human actually named?

    An empty ``merchant_scope`` means the human named none — which is not the
    same as "any merchant is fine". The mandate's allowlist governs instead, and
    saying so explicitly keeps the two from being confused.
    """
    if not intent.merchant_scope:
        ok = mandate.covers_merchant(cart.merchant_id)
        return _result(
            Dimension.MERCHANT_SCOPE,
            [ReasonCode.MERCHANT_UNNAMED_BY_HUMAN] if ok else [ReasonCode.MERCHANT_OUT_OF_SCOPE],
            ok=ok,
        )
    if cart.merchant_id in intent.merchant_scope:
        return _result(Dimension.MERCHANT_SCOPE, [ReasonCode.MERCHANT_IN_SCOPE], ok=True)
    return _result(Dimension.MERCHANT_SCOPE, [ReasonCode.MERCHANT_OUT_OF_SCOPE], ok=False)


def check_category_scope(intent: Intent, cart: Cart, snapshot: CatalogSnapshot) -> DimensionResult:
    """Does everything fall inside the categories the human asked about?"""
    if intent.category_scope is None:
        return _result(Dimension.CATEGORY_SCOPE, [ReasonCode.CATEGORY_IN_SCOPE], ok=True)

    allowed = set(intent.category_scope)
    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is not None and item.category not in allowed:
            return _result(Dimension.CATEGORY_SCOPE, [ReasonCode.CATEGORY_OUT_OF_SCOPE], ok=False)
    return _result(Dimension.CATEGORY_SCOPE, [ReasonCode.CATEGORY_IN_SCOPE], ok=True)


def check_mandate(
    mandate: Mandate,
    cart: Cart,
    snapshot: CatalogSnapshot,
    *,
    verified_total: int,
    evaluated_at: str,
) -> DimensionResult:
    """Was this spend permitted at all?

    Separate from every other check on purpose. The mandate answers "was this
    permitted", and the rest of the gate answers "was this what was asked for".
    The whole project exists because those are different questions.
    """
    codes: list[ReasonCode] = []

    if mandate.revoked:
        codes.append(ReasonCode.MANDATE_REVOKED)
    elif not mandate.active_at(evaluated_at):
        codes.append(
            ReasonCode.MANDATE_NOT_YET_VALID
            if evaluated_at < mandate.valid_from
            else ReasonCode.MANDATE_EXPIRED
        )

    if not mandate.covers_merchant(cart.merchant_id):
        codes.append(ReasonCode.MANDATE_MERCHANT_NOT_ALLOWED)

    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is not None and not mandate.covers_category(item.category):
            codes.append(ReasonCode.MANDATE_CATEGORY_NOT_ALLOWED)
            break

    if verified_total > mandate.per_transaction_cap_paise:
        codes.append(ReasonCode.MANDATE_PER_TXN_EXCEEDED)
    if verified_total > mandate.max_amount_paise:
        codes.append(ReasonCode.MANDATE_TOTAL_EXCEEDED)

    if codes:
        return _result(Dimension.MANDATE, _dedupe(codes), ok=False)
    return _result(Dimension.MANDATE, [ReasonCode.MANDATE_SATISFIED], ok=True)


def check_sanitization(cart: Cart, snapshot: CatalogSnapshot) -> DimensionResult:
    """Did any catalog copy behind this order trip the ingest sanitizer?

    The sanitizer already stripped the content on the way in, so this is not
    the defence — it is the *record* that a defence fired, carried forward so a
    decision made against poisoned copy is visibly one.
    """
    flags = []
    for line in cart.lines:
        item = snapshot.find(line.item_id)
        if item is not None:
            flags.extend(item.sanitization.flags)

    if not flags:
        return _result(Dimension.SANITIZATION, [ReasonCode.SANITIZER_CLEAN], ok=True)

    mapping = {
        "INSTRUCTION_LIKE": ReasonCode.SANITIZER_INSTRUCTION_LIKE,
        "HIDDEN_TEXT": ReasonCode.SANITIZER_HIDDEN_TEXT,
        "ENCODED_PAYLOAD": ReasonCode.SANITIZER_ENCODED_PAYLOAD,
        "DIRECTION_OVERRIDE": ReasonCode.SANITIZER_DIRECTION_OVERRIDE,
        "PRICE_CLAIM": ReasonCode.SANITIZER_PRICE_CLAIM,
    }
    codes = _dedupe([mapping[str(flag)] for flag in flags])
    return DimensionResult(
        dimension=Dimension.SANITIZATION,
        # Not a hard failure: the content never reached the agent. It lowers the
        # score and shows up in the reasons, which is what a merchant needs to
        # know when deciding whether to trust a supplier's feed.
        status=DimensionStatus.UNCERTAIN,
        score_bp=3_000,
        reason_codes=codes,
    )


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    return list(dict.fromkeys(codes))
