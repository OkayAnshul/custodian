"""A second substitution tie-breaker, on a different provider.

This exists to prove something the README can otherwise only assert: **the model
is a component, not the system.** `SemanticScorer` is a Protocol; `ClaudeScorer`
and `GroqScorer` both satisfy it, both are graded by one contract suite, and
`decide()` does not know which one ran. Swap the provider and the decisions
still replay, because what replay reads is the recorded verdict rather than the
thing that produced it.

Everything above the transport is shared with `semantic.py` — the same system
prompt, the same output schema, the same `prompt_digest`, the same verdict
construction. Only the wire format differs, and that is the entire point. Three
things differ from Anthropic's:

- the system prompt is a message with ``role: "system"`` rather than a separate
  parameter;
- structured output is ``response_format={"type": "json_schema", "json_schema":
  {...}}`` rather than ``output_config.format``;
- the text comes back at ``choices[0].message.content`` rather than from a
  content-block list.

``prompt_digest`` deliberately does *not* include the model. Two providers asked
the same question produce the same digest, and the model is recorded separately
on the verdict — so the ledger can show one question answered two ways, which is
what makes a provider comparison possible at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from custodian.gate.semantic import (
    OUTPUT_SCHEMA,
    SYSTEM,
    ScoringError,
    _verdict_from,
    build_question,
    prompt_digest,
)
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem
from custodian.schemas.verdict import SemanticVerdict

#: Groq enforces `strict: true` — genuine constrained decoding rather than a
#: request to please return JSON — on a short list of models. Using one off that
#: list would make "the schema is enforced" a hope. The 120b is the largest of
#: them, and this is a judgment about cooking, which is the one place in this
#: system where model capability actually changes the answer.
DEFAULT_MODEL: Final[str] = "openai/gpt-oss-120b"

#: Models where `strict` is honoured. Anything else silently degrades to a
#: suggestion, so the constructor refuses rather than letting that pass.
STRICT_MODELS: Final[frozenset[str]] = frozenset({
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
})


@dataclass
class GroqScorer:
    """The substitution tie-breaker, on Groq."""

    model_id: str = DEFAULT_MODEL
    max_tokens: int = 1_024
    #: Zero, because this is a judgment that should not vary between two runs of
    #: the same question. A verdict that changes on re-ask is a verdict the
    #: ledger cannot stand behind.
    temperature: float = 0.0
    client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.model_id not in STRICT_MODELS:
            raise ScoringError(
                f"{self.model_id!r} does not honour strict schema enforcement on Groq. "
                f"Choose one of {sorted(STRICT_MODELS)} — an unenforced schema turns "
                f"'the output is constrained' into a hope."
            )
        if self.client is None:
            try:
                from groq import Groq
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise ScoringError("the groq package is required for GroqScorer") from exc
            self.client = Groq()

    @property
    def model(self) -> str:
        return self.model_id

    def score(
        self, *, goal: str, requested: RequestedItem, offered: CatalogItem, cart_line_id: str
    ) -> SemanticVerdict:
        import groq

        question = build_question(goal, requested, offered)
        digest = prompt_digest(goal, requested, offered)

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": question},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "substitution_verdict",
                        "strict": True,
                        "schema": OUTPUT_SCHEMA,
                    },
                },
            )
        except groq.RateLimitError as exc:
            # Free tiers rate-limit. Surfacing this as its own message matters:
            # a rate limit is a reason to wait, and a refusal is a reason to hold.
            raise ScoringError(f"rate limited while scoring: {exc}") from exc
        except groq.APIStatusError as exc:
            raise ScoringError(f"groq returned {exc.status_code} while scoring") from exc
        except groq.APIConnectionError as exc:
            raise ScoringError(f"could not reach groq to score: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        if choice is None or not (choice.message.content or "").strip():
            raise ScoringError("groq returned no content")
        if getattr(choice, "finish_reason", None) == "length":
            # A truncated JSON object parses as malformed rather than as a
            # verdict, and saying which it was beats a parse error.
            raise ScoringError("groq response was cut off before the verdict was complete")

        raw = choice.message.content
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ScoringError(f"groq response was not valid JSON: {exc}") from exc

        return _verdict_from(
            payload, cart_line_id=cart_line_id, requested_line_id=requested.line_id,
            model=self.model_id, digest=digest, raw=raw,
        )
