"""The closed set of reasons a decision can give.

Explainability here is a byproduct of decomposition, not a feature bolted on:
every check emits a code from this enum, and the human-readable text is
rendered from the code plus its parameters. Free-form explanation is
deliberately absent — a reason string an LLM wrote is not evidence, and
"why did Custodian hold this order?" must be answerable without calling a model.

Codes are grouped by the dimension that raises them. A code is never reused
across dimensions, so a code alone identifies where in the gate it came from.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ReasonCode(StrEnum):
    # --- price integrity: the agent's claim against the catalog -------------
    PRICE_MATCHES_CATALOG = "PRICE_MATCHES_CATALOG"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    ITEM_NOT_IN_CATALOG = "ITEM_NOT_IN_CATALOG"
    ITEM_OUT_OF_STOCK = "ITEM_OUT_OF_STOCK"
    SNAPSHOT_STALE = "SNAPSHOT_STALE"

    # --- budget: the human's ceiling ---------------------------------------
    BUDGET_SATISFIED = "BUDGET_SATISFIED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    BUDGET_UNSET = "BUDGET_UNSET"
    UNIT_PRICE_CEILING_EXCEEDED = "UNIT_PRICE_CEILING_EXCEEDED"

    # --- merchant and category scope ---------------------------------------
    MERCHANT_IN_SCOPE = "MERCHANT_IN_SCOPE"
    MERCHANT_OUT_OF_SCOPE = "MERCHANT_OUT_OF_SCOPE"
    MERCHANT_UNNAMED_BY_HUMAN = "MERCHANT_UNNAMED_BY_HUMAN"
    CATEGORY_IN_SCOPE = "CATEGORY_IN_SCOPE"
    CATEGORY_OUT_OF_SCOPE = "CATEGORY_OUT_OF_SCOPE"

    # --- mandate: was the spend permitted at all ---------------------------
    MANDATE_SATISFIED = "MANDATE_SATISFIED"
    MANDATE_TOTAL_EXCEEDED = "MANDATE_TOTAL_EXCEEDED"
    MANDATE_PER_TXN_EXCEEDED = "MANDATE_PER_TXN_EXCEEDED"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"
    MANDATE_NOT_YET_VALID = "MANDATE_NOT_YET_VALID"
    MANDATE_REVOKED = "MANDATE_REVOKED"
    MANDATE_MERCHANT_NOT_ALLOWED = "MANDATE_MERCHANT_NOT_ALLOWED"
    MANDATE_CATEGORY_NOT_ALLOWED = "MANDATE_CATEGORY_NOT_ALLOWED"
    MANDATE_CURRENCY_MISMATCH = "MANDATE_CURRENCY_MISMATCH"

    # --- substitution fidelity (ADR-007) -----------------------------------
    SUBST_EXACT = "SUBST_EXACT"
    SUBST_FORM_COMPATIBLE = "SUBST_FORM_COMPATIBLE"
    SUBST_FORM_INCOMPATIBLE = "SUBST_FORM_INCOMPATIBLE"
    SUBST_BASE_CHANGED = "SUBST_BASE_CHANGED"
    SUBST_POLICY_FORBIDS = "SUBST_POLICY_FORBIDS"
    SUBST_FORM_UNLISTED = "SUBST_FORM_UNLISTED"          # escalates
    SUBST_BASE_UNKNOWN = "SUBST_BASE_UNKNOWN"            # escalates
    SUBST_BUNDLE_CANDIDATE = "SUBST_BUNDLE_CANDIDATE"    # escalates
    SUBST_MODEL_FAITHFUL = "SUBST_MODEL_FAITHFUL"
    SUBST_MODEL_UNFAITHFUL = "SUBST_MODEL_UNFAITHFUL"
    SUBST_MODEL_UNSURE = "SUBST_MODEL_UNSURE"
    SUBST_VERDICT_MISSING = "SUBST_VERDICT_MISSING"

    # --- scope creep: did unrequested things appear -------------------------
    SCOPE_CLEAN = "SCOPE_CLEAN"
    SCOPE_UNREQUESTED_ITEM = "SCOPE_UNREQUESTED_ITEM"
    SCOPE_QUANTITY_INFLATED = "SCOPE_QUANTITY_INFLATED"
    SCOPE_REQUESTED_ITEM_MISSING = "SCOPE_REQUESTED_ITEM_MISSING"

    # --- sanitization: what the merchant's own copy tried to do -------------
    SANITIZER_CLEAN = "SANITIZER_CLEAN"
    SANITIZER_INSTRUCTION_LIKE = "SANITIZER_INSTRUCTION_LIKE"
    SANITIZER_HIDDEN_TEXT = "SANITIZER_HIDDEN_TEXT"
    SANITIZER_ENCODED_PAYLOAD = "SANITIZER_ENCODED_PAYLOAD"
    SANITIZER_DIRECTION_OVERRIDE = "SANITIZER_DIRECTION_OVERRIDE"
    SANITIZER_PRICE_CLAIM = "SANITIZER_PRICE_CLAIM"

    # --- overall disposition -----------------------------------------------
    CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"
    ALIGNMENT_BELOW_APPROVE_THRESHOLD = "ALIGNMENT_BELOW_APPROVE_THRESHOLD"
    HARD_CONSTRAINT_VIOLATED = "HARD_CONSTRAINT_VIOLATED"


#: One line per code, written for a merchant reading a held order — not for an
#: engineer reading a stack trace.
EXPLANATION: Final[dict[ReasonCode, str]] = {
    ReasonCode.PRICE_MATCHES_CATALOG: "Every price the agent quoted matches the catalog.",
    ReasonCode.PRICE_MISMATCH: "The agent quoted a price the catalog does not have.",
    ReasonCode.ITEM_NOT_IN_CATALOG: "The cart contains an item this catalog does not sell.",
    ReasonCode.ITEM_OUT_OF_STOCK: "The cart contains an item that is out of stock.",
    ReasonCode.SNAPSHOT_STALE: "The catalog snapshot is older than this decision allows.",

    ReasonCode.BUDGET_SATISFIED: "The verified total is within the stated budget.",
    ReasonCode.BUDGET_EXCEEDED: "The verified total exceeds the stated budget.",
    ReasonCode.BUDGET_UNSET: "No budget was stated; the mandate's caps govern instead.",
    ReasonCode.UNIT_PRICE_CEILING_EXCEEDED: "An item costs more per unit than was allowed for it.",

    ReasonCode.MERCHANT_IN_SCOPE: "The merchant is one the human named.",
    ReasonCode.MERCHANT_OUT_OF_SCOPE: "The purchase is from a merchant the human did not name.",
    ReasonCode.MERCHANT_UNNAMED_BY_HUMAN: "The human named no merchant; the mandate's allowlist governs.",
    ReasonCode.CATEGORY_IN_SCOPE: "Every item falls in a category the human asked about.",
    ReasonCode.CATEGORY_OUT_OF_SCOPE: "An item falls outside the categories the human asked about.",

    ReasonCode.MANDATE_SATISFIED: "The spend is inside the payment mandate.",
    ReasonCode.MANDATE_TOTAL_EXCEEDED: "The spend exceeds the mandate's lifetime ceiling.",
    ReasonCode.MANDATE_PER_TXN_EXCEEDED: "The spend exceeds the mandate's per-transaction cap.",
    ReasonCode.MANDATE_EXPIRED: "The payment mandate has expired.",
    ReasonCode.MANDATE_NOT_YET_VALID: "The payment mandate is not valid yet.",
    ReasonCode.MANDATE_REVOKED: "The payment mandate has been revoked.",
    ReasonCode.MANDATE_MERCHANT_NOT_ALLOWED: "The mandate does not authorise payment to this merchant.",
    ReasonCode.MANDATE_CATEGORY_NOT_ALLOWED: "The mandate does not cover this category of spending.",
    ReasonCode.MANDATE_CURRENCY_MISMATCH: "The mandate is denominated in a different currency.",

    ReasonCode.SUBST_EXACT: "The agent bought exactly what was asked for.",
    ReasonCode.SUBST_FORM_COMPATIBLE: "A substitution kept the same base ingredient in a compatible form.",
    ReasonCode.SUBST_FORM_INCOMPATIBLE: "A substitution changed the form in a way that does not preserve intent.",
    ReasonCode.SUBST_BASE_CHANGED: "A substitution changed the base ingredient.",
    ReasonCode.SUBST_POLICY_FORBIDS: "A substitution was made that the human's substitution policy does not permit.",
    ReasonCode.SUBST_FORM_UNLISTED: "A substitution pairs two forms with no recorded relationship.",
    ReasonCode.SUBST_BASE_UNKNOWN: "An item could not be placed in the catalog taxonomy.",
    ReasonCode.SUBST_BUNDLE_CANDIDATE: "Several items appear to stand in for one request, or vice versa.",
    ReasonCode.SUBST_MODEL_FAITHFUL: "On review, the substitution preserves what was asked for.",
    ReasonCode.SUBST_MODEL_UNFAITHFUL: "On review, the substitution does not preserve what was asked for.",
    ReasonCode.SUBST_MODEL_UNSURE: "The substitution could not be settled either way.",
    ReasonCode.SUBST_VERDICT_MISSING: "A substitution needed review and no review was recorded.",

    ReasonCode.SCOPE_CLEAN: "Every item in the cart traces to something that was asked for.",
    ReasonCode.SCOPE_UNREQUESTED_ITEM: "The cart contains an item nothing in the request asked for.",
    ReasonCode.SCOPE_QUANTITY_INFLATED: "The cart contains more of an item than was asked for.",
    ReasonCode.SCOPE_REQUESTED_ITEM_MISSING: "Something that was asked for is not in the cart.",

    ReasonCode.SANITIZER_CLEAN: "No catalog copy behind this order tripped the sanitizer.",
    ReasonCode.SANITIZER_INSTRUCTION_LIKE: "Catalog copy contained text written to instruct an agent.",
    ReasonCode.SANITIZER_HIDDEN_TEXT: "Catalog copy contained text hidden from human readers.",
    ReasonCode.SANITIZER_ENCODED_PAYLOAD: "Catalog copy contained an encoded payload.",
    ReasonCode.SANITIZER_DIRECTION_OVERRIDE: "Catalog copy used text-direction characters to disguise its content.",
    ReasonCode.SANITIZER_PRICE_CLAIM: "Catalog copy asserted its own price rather than leaving it to the price field.",

    ReasonCode.CONFIDENCE_BELOW_THRESHOLD: "The gate was not confident enough to decide, so it asked.",
    ReasonCode.ALIGNMENT_BELOW_APPROVE_THRESHOLD: "The cart does not match the request closely enough to approve.",
    ReasonCode.HARD_CONSTRAINT_VIOLATED: "A constraint that cannot be traded off was violated.",
}

#: Codes that reject on their own authority, without reference to any score.
#: Deterministic checks run first precisely so these settle a case before the
#: semantic scorer ever sees it.
BLOCKING: Final[frozenset[ReasonCode]] = frozenset({
    ReasonCode.PRICE_MISMATCH,
    ReasonCode.ITEM_NOT_IN_CATALOG,
    ReasonCode.ITEM_OUT_OF_STOCK,
    ReasonCode.BUDGET_EXCEEDED,
    ReasonCode.UNIT_PRICE_CEILING_EXCEEDED,
    ReasonCode.MERCHANT_OUT_OF_SCOPE,
    ReasonCode.MANDATE_TOTAL_EXCEEDED,
    ReasonCode.MANDATE_PER_TXN_EXCEEDED,
    ReasonCode.MANDATE_EXPIRED,
    ReasonCode.MANDATE_NOT_YET_VALID,
    ReasonCode.MANDATE_REVOKED,
    ReasonCode.MANDATE_MERCHANT_NOT_ALLOWED,
    ReasonCode.MANDATE_CATEGORY_NOT_ALLOWED,
    ReasonCode.MANDATE_CURRENCY_MISMATCH,
    ReasonCode.SUBST_POLICY_FORBIDS,
    ReasonCode.HARD_CONSTRAINT_VIOLATED,
})


def explain(code: ReasonCode) -> str:
    """Human-readable text for a code."""
    return EXPLANATION[ReasonCode(code)]


def is_blocking(code: ReasonCode) -> bool:
    """Whether this code rejects on its own authority."""
    return ReasonCode(code) in BLOCKING
