"""The live intent parser — model position #1 of two.

Uses structured outputs (``output_config.format``) rather than free-form text or
tool use. The model's response is constrained to ``prompt.OUTPUT_SCHEMA`` by the
API itself, so "the model returned something unparseable" stops being a failure
mode the gate has to handle at runtime.

The raw response string is kept alongside the parsed object and written to the
ledger. A parsed object alone is not evidence — it is our reading of the model's
answer, and a dispute may need to see the answer.

This class is never imported by ``gate.decide``. Replay reads the recorded
response; it does not re-ask (ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custodian.clock import utc_now
from custodian.ingest.taxonomy import Taxonomy
from custodian.intent import prompt as prompt_module
from custodian.intent.parser import ParseError, ParseResult, decode, resolve

#: Opus 5 unless the caller says otherwise. Intent parsing is the only place in
#: this system where language understanding is load-bearing, and it runs once
#: per request — this is not the line item worth economising on.
DEFAULT_MODEL = "claude-opus-5"

#: Effort for a short structured extraction. Medium rather than low because a
#: misread constraint ("under ₹2,000" attached to the wrong item) propagates
#: into every downstream check as though the human had said it.
DEFAULT_EFFORT = "medium"


@dataclass
class ClaudeParser:
    """Parses a shopping request with Claude, under a constrained output schema."""

    model_id: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = 4_096
    taxonomy: Taxonomy | None = None
    client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise ParseError(
                    "the anthropic package is required for live parsing; "
                    "use RecordedParser for offline work"
                ) from exc
            self.client = anthropic.Anthropic()

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
        import anthropic

        try:
            response = self.client.messages.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                system=prompt_module.SYSTEM,
                messages=[{"role": "user", "content": user_message}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": prompt_module.OUTPUT_SCHEMA},
                },
            )
        except anthropic.RateLimitError as exc:
            raise ParseError(f"rate limited while parsing intent: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ParseError(f"model returned {exc.status_code} while parsing intent") from exc
        except anthropic.APIConnectionError as exc:
            raise ParseError(f"could not reach the model to parse intent: {exc}") from exc

        # A refusal is an outcome to surface, not an exception to swallow. The
        # request still has no structured intent, so it cannot proceed — but the
        # reason belongs in the error rather than as a parse failure.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise ParseError(f"model declined to parse this request (category: {category})")

        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            raise ParseError(f"model returned no text block (stop_reason={response.stop_reason})")
        return text
