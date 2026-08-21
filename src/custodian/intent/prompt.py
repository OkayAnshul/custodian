"""The one prompt in the system that reads natural language.

Kept in its own module and hashed, because the prompt is part of the evidence.
A recorded parse whose prompt cannot be identified is not reproducible, and
"the model was asked something like this" is not an audit trail.

The prompt asks for less than it could. It does **not** ask the model to
classify items into categories or to identify base ingredients — those come
from the same lexicon the catalog is normalised against (``ingest.taxonomy``),
so that both sides of the comparison speak one vocabulary. A model-assigned
category would be a second, disagreeing opinion about what a word means.

What is genuinely left to language understanding: pulling structure out of a
sentence a human typed. That is model position #1 of two.
"""

from __future__ import annotations

from typing import Final

from custodian.canonical import canonical_hash

SYSTEM: Final[str] = """\
You extract structure from a shopping request. You do not make purchasing \
decisions, evaluate prices, or judge whether anything is a good idea.

Return the request as data. Rules:

- `goal` is the human's request, copied verbatim.
- `requested_items` lists each distinct thing asked for. Use the human's own \
words in `raw_text`; do not translate, expand, or normalise them.
- `quantity` is how many units were asked for. Default to 1 when unstated.
- `budget_paise` is any total spending limit, in paise (₹1 = 100 paise). Null if \
none was stated.
- `max_unit_price_paise` is a per-item price ceiling, in paise. Null if none.
- `merchant_scope` lists merchants named by the human. Empty if none were named.
- `category_scope` lists categories the human restricted the request to. Null if \
they did not restrict it.
- `substitution_policy` is EXACT_ONLY if the human ruled out substitutes, \
EQUIVALENT if they invited them ("or similar", "whatever works"), otherwise \
SAME_BASE.

Never infer a budget that was not stated. Never add an item that was not asked \
for. If the request is ambiguous, represent the ambiguity rather than resolving \
it — something downstream is built to handle not knowing, and a guess here \
cannot be distinguished from a fact later."""

#: JSON Schema the model's output must satisfy. Free-form text is not accepted.
OUTPUT_SCHEMA: Final[dict] = {
    "type": "object",
    "required": ["goal", "requested_items", "substitution_policy"],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string"},
        "budget_paise": {"type": ["integer", "null"], "minimum": 0},
        "merchant_scope": {"type": "array", "items": {"type": "string"}},
        "category_scope": {"type": ["array", "null"], "items": {"type": "string"}},
        "substitution_policy": {"type": "string", "enum": ["EXACT_ONLY", "SAME_BASE", "EQUIVALENT"]},
        "requested_items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["raw_text", "quantity"],
                "additionalProperties": False,
                "properties": {
                    "raw_text": {"type": "string", "minLength": 1},
                    "quantity": {"type": "integer", "minimum": 1},
                    "max_unit_price_paise": {"type": ["integer", "null"], "minimum": 0},
                },
            },
        },
    },
}

#: Bumped whenever SYSTEM or OUTPUT_SCHEMA changes, so a replayed parse can tell
#: a prompt change from a model change.
VERSION: Final[str] = "intent-prompt-v1"


def build(goal: str) -> tuple[str, str]:
    """Return the user message and the digest identifying this exact prompt."""
    user = f"Shopping request:\n\n{goal.strip()}"
    return user, prompt_digest(goal)


def prompt_digest(goal: str) -> str:
    """Hash of everything that determined the model's input."""
    return canonical_hash(
        {"version": VERSION, "system": SYSTEM, "schema": OUTPUT_SCHEMA, "goal": goal.strip()}
    )
