"""Natural language in, structured intent out — model position #1 of two.

The parser is behind an interface for the same reason the payment gateway is: a
live API key must not be a precondition for building or testing anything else.
``RecordedParser`` replays fixtures by prompt digest; ``ClaudeParser`` calls the
model. Both satisfy ``IntentParser`` and both pass one contract suite.

Two structural points about where the model sits.

**Its output is recorded as an observation.** ``ParseResult`` carries the model
id, the prompt digest and the raw response, and those go to the ledger. Replay
reads the recorded parse rather than re-asking, which is what makes a decision
reproducible without a model (ADR-010).

**Attribute resolution is deterministic, not model work.** The model returns the
human's own words; ``resolve`` then places each requested item through the same
taxonomy the catalog was normalised with. Asking the model for a category would
introduce a second opinion about what a word means, and the gate compares the
request against the catalog — one vocabulary or the comparison is meaningless.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from custodian.ingest.taxonomy import Taxonomy, default_taxonomy
from custodian.intent import prompt as prompt_module
from custodian.schemas.intent import Intent, RequestedItem, SubstitutionPolicy
from custodian.schemas.types import Digest, Timestamp


class ParseError(RuntimeError):
    """The model's output could not be turned into a structured intent."""


@dataclass(frozen=True, slots=True)
class ParseResult:
    """A structured intent, with the provenance to reproduce it."""

    intent: Intent
    model: str
    prompt_digest: Digest
    raw_response: str
    obtained_at: Timestamp

    def as_observed(self) -> dict[str, Any]:
        """The ledger-safe view: what the model was asked and what it returned."""
        return {
            "model": self.model,
            "prompt_version": prompt_module.VERSION,
            "prompt_digest": self.prompt_digest,
            "raw_response": self.raw_response,
            "obtained_at": self.obtained_at,
        }


@runtime_checkable
class IntentParser(Protocol):
    """What Custodian requires of an intent parser."""

    @property
    def model(self) -> str:
        """Identifier recorded in the ledger, so a parse names its source."""
        ...

    def parse(self, goal: str, *, intent_id: str) -> ParseResult:
        """Turn a human's request into a structured intent."""
        ...


def resolve(
    payload: dict[str, Any], *, intent_id: str, taxonomy: Taxonomy | None = None
) -> Intent:
    """Build an ``Intent`` from a model payload, placing items deterministically.

    Raises ``ParseError`` rather than repairing a malformed payload. A parser
    that quietly fixes up model output is deciding what the human meant, which
    is the thing this whole system exists to stop something else doing.
    """
    tax = taxonomy or default_taxonomy()
    if not isinstance(payload, dict):
        raise ParseError(f"expected an object, got {type(payload).__name__}")

    raw_items = payload.get("requested_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ParseError("model returned no requested items")

    items: list[RequestedItem] = []
    for index, entry in enumerate(raw_items):
        if not isinstance(entry, dict) or not entry.get("raw_text"):
            raise ParseError(f"requested_items[{index}] has no raw_text")
        placement = tax.place(entry["raw_text"])
        items.append(
            RequestedItem(
                line_id=f"{intent_id}-r{index + 1}",
                raw_text=entry["raw_text"],
                quantity=entry.get("quantity") or 1,
                base=placement.base,
                form=placement.form,
                category=placement.category,
                max_unit_price_paise=entry.get("max_unit_price_paise"),
            )
        )

    try:
        return Intent(
            intent_id=intent_id,
            goal=payload.get("goal") or "",
            budget_paise=payload.get("budget_paise"),
            merchant_scope=tuple(payload.get("merchant_scope") or ()),
            category_scope=(
                tuple(payload["category_scope"]) if payload.get("category_scope") else None
            ),
            requested_items=tuple(items),
            substitution_policy=SubstitutionPolicy(
                payload.get("substitution_policy") or SubstitutionPolicy.SAME_BASE
            ),
        )
    except (ValueError, TypeError) as exc:
        raise ParseError(f"model output does not satisfy the intent contract: {exc}") from exc


def decode(raw_response: str) -> dict[str, Any]:
    """Parse the model's response as JSON, with a useful error if it is not."""
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ParseError(f"model response was not valid JSON: {exc}") from exc
