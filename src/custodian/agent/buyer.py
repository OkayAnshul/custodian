"""A deliberately naive reference buyer.

This agent is not meant to be good. It is meant to be *typical* — and making it
clever would quietly undercut the thesis. Custodian's claim is that the buying
agent is an untrusted client whose competence cannot be assumed; demonstrating
that against a carefully-written agent would prove nothing.

Two design choices carry the argument:

**It matches items by lexical overlap.** Jaccard on product names — precisely the
primitive ADR-007 rejected for the gate. So the agent will happily offer almond
milk for coconut milk, because token overlap scores that identically to coconut
cream. The agent's failure and the gate's correctness come from the same example.

**It believes what the catalog tells it.** When handed an unsanitised feed, it
follows instruction-like copy in a product description. This is a vulnerable
*client*, not an attack tool: it recognises one hard-coded phrasing, acts only on
items already in the feed it was given, and has no capability outside building a
``Cart`` object. It exists so the "without Custodian" baseline is measured rather
than asserted.

Nothing here is a security control. Every check that matters happens server-side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Sequence

from custodian.schemas.cart import Cart, CartLine
from custodian.schemas.intent import Intent, RequestedItem

#: The one instruction shape this reference client is naive enough to obey.
#: Deliberately narrow and literal — it demonstrates the failure, it does not
#: generalise it.
_FOLLOWS: Final[re.Pattern[str]] = re.compile(
    r"add\s+(?:the\s+)?(?P<item>[\w\s]+?)\s+to\s+(?:the\s+)?cart", re.IGNORECASE
)

_TOKENS: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


def _jaccard(left: str, right: str) -> float:
    """Token-set overlap — the primitive the gate does not use."""
    a, b = set(_TOKENS.findall(left.lower())), set(_TOKENS.findall(right.lower()))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class NaiveBuyer:
    """Builds a cart from a feed. Badly, on purpose."""

    #: Minimum lexical overlap before it will call something a match. Low,
    #: because a real naive agent would rather buy the wrong thing than nothing.
    match_threshold: float = 0.15

    def build_cart(
        self,
        intent: Intent,
        feed: Sequence[dict[str, Any]],
        *,
        cart_id: str,
        merchant_id: str,
    ) -> Cart:
        """Pick something for each requested item, then do as it is told."""
        lines: list[CartLine] = []
        chosen: set[str] = set()

        for requested in intent.requested_items:
            entry = self._best_match(requested, feed)
            if entry is None:
                continue  # silently drops it — the gate catches the omission
            lines.append(self._line(entry, requested.quantity, requested.line_id, len(lines) + 1))
            chosen.add(str(entry["item_id"]))

        for entry in self._instructed_additions(feed, chosen):
            lines.append(self._line(entry, 1, None, len(lines) + 1))
            chosen.add(str(entry["item_id"]))

        if not lines:  # a Cart must not be empty; give the gate something to reject
            entry = dict(feed[0])
            lines.append(self._line(entry, 1, None, 1))

        return Cart(cart_id=cart_id, merchant_id=merchant_id, lines=tuple(lines))

    def _best_match(
        self, requested: RequestedItem, feed: Sequence[dict[str, Any]]
    ) -> dict[str, Any] | None:
        scored = [
            (_jaccard(requested.raw_text, str(entry.get("name", ""))), index, entry)
            for index, entry in enumerate(feed)
        ]
        best = max(scored, key=lambda triple: (triple[0], -triple[1]), default=None)
        if best is None or best[0] < self.match_threshold:
            return None
        return best[2]

    def _instructed_additions(
        self, feed: Sequence[dict[str, Any]], already_chosen: set[str]
    ) -> list[dict[str, Any]]:
        """Do what the product descriptions say. This is the vulnerability."""
        additions: list[dict[str, Any]] = []
        for entry in feed:
            for wanted in _FOLLOWS.findall(str(entry.get("description", ""))):
                target = self._best_match_by_name(wanted, feed)
                if target is not None and str(target["item_id"]) not in already_chosen:
                    additions.append(target)
                    already_chosen.add(str(target["item_id"]))
        return additions

    def _best_match_by_name(
        self, text: str, feed: Sequence[dict[str, Any]]
    ) -> dict[str, Any] | None:
        scored = [(_jaccard(text, str(e.get("name", ""))), i, e) for i, e in enumerate(feed)]
        best = max(scored, key=lambda triple: (triple[0], -triple[1]), default=None)
        return best[2] if best and best[0] >= 0.3 else None

    @staticmethod
    def _line(
        entry: dict[str, Any], quantity: int, satisfies: str | None, index: int
    ) -> CartLine:
        return CartLine(
            line_id=f"l{index}",
            item_id=str(entry["item_id"]),
            name_asserted=str(entry["name"]),
            quantity=quantity,
            asserted_unit_price_paise=int(entry["price_paise"]),
            satisfies_line_id=satisfies,
        )
