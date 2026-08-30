"""Intent parsing on Groq — the second implementation of model position #1.

Exists for the same reason `gate.groq_scorer` does: the Protocol is only
demonstrated by a second provider behind it. With this and `GroqScorer`, both of
the system's two model positions have a free-tier implementation, and the whole
project runs end to end without a paid API key.

Everything above the transport is shared with `intent.claude` — the same system
prompt from `intent.prompt`, the same output schema, the same `prompt_digest`,
the same deterministic `resolve` that places the model's words through the
taxonomy. Only the wire format differs.

The nesting is worth noting because it bit once: Groq wraps the schema as
``response_format.json_schema.schema``, so the shared `OUTPUT_SCHEMA` sits two
levels down rather than one. Same schema object, different envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from custodian.clock import utc_now
from custodian.gate.groq_scorer import STRICT_MODELS
from custodian.ingest.taxonomy import Taxonomy
from custodian.intent import prompt as prompt_module
from custodian.intent.parser import ParseError, ParseResult, decode, resolve

#: The same strict-decoding constraint the scorer applies, for the same reason:
#: an unenforced schema makes "the model's output is constrained" a hope.
DEFAULT_MODEL: Final[str] = "openai/gpt-oss-120b"


@dataclass
class GroqParser:
    """Parses a shopping request on Groq, under a constrained output schema."""

    model_id: str = DEFAULT_MODEL
    max_tokens: int = 2_048
    #: Zero. Two runs of the same request must produce the same structured
    #: intent, or the ledger records something that cannot be reproduced.
    temperature: float = 0.0
    taxonomy: Taxonomy | None = None
    client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.model_id not in STRICT_MODELS:
            raise ParseError(
                f"{self.model_id!r} does not honour strict schema enforcement on Groq. "
                f"Choose one of {sorted(STRICT_MODELS)}."
            )
        if self.client is None:
            try:
                from groq import Groq
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise ParseError("the groq package is required for GroqParser") from exc
            self.client = Groq()

    @property
    def model(self) -> str:
        return self.model_id

    def parse(self, goal: str, *, intent_id: str) -> ParseResult:
        """Turn a human's request into a structured intent."""
        if not goal or not goal.strip():
            raise ParseError("cannot parse an empty request")

        user_message, digest = prompt_module.build(goal)
        raw = self._request(user_message)

        return ParseResult(
            intent=resolve(decode(raw), intent_id=intent_id, taxonomy=self.taxonomy),
            model=self.model_id,
            prompt_digest=digest,
            raw_response=raw,
            obtained_at=utc_now(),
        )

    def _request(self, user_message: str) -> str:
        """Call the model and return the raw JSON text it produced."""
        import groq

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": prompt_module.SYSTEM},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "shopping_intent",
                        "strict": True,
                        "schema": prompt_module.OUTPUT_SCHEMA,
                    },
                },
            )
        except groq.RateLimitError as exc:
            raise ParseError(f"rate limited while parsing intent: {exc}") from exc
        except groq.APIStatusError as exc:
            raise ParseError(f"model returned {exc.status_code} while parsing intent") from exc
        except groq.APIConnectionError as exc:
            raise ParseError(f"could not reach the model to parse intent: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        if choice is None or not (choice.message.content or "").strip():
            raise ParseError("model returned no content")
        if getattr(choice, "finish_reason", None) == "length":
            raise ParseError("model response was cut off before the intent was complete")
        return choice.message.content
