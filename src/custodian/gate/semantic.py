"""Substitution tie-breaking — model position #2 of two.

Reached only for cases the deterministic layer explicitly could not settle: an
unlisted form pair, an ingredient the taxonomy could not place, a bundle. Every
other substitution is decided by the attribute tables without a model, which is
why this runs on a handful of lines per order rather than all of them.

What the model is asked is deliberately narrow. Not "should this purchase go
ahead" — it never sees the budget, the mandate, or the total. Just: does this
item preserve what was asked for? The gate decides what to do with the answer.

The output schema offers ``UNSURE`` as a first-class label. A two-way choice
manufactures confidence, and a model forced to pick between FAITHFUL and
UNFAITHFUL on a genuinely ambiguous pair will pick one. ``UNSURE`` routes to
hold, which is the honest destination.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from custodian.canonical import canonical_hash
from custodian.clock import utc_now
from custodian.schemas.catalog import CatalogItem
from custodian.schemas.intent import RequestedItem
from custodian.schemas.verdict import SemanticVerdict, VerdictLabel

SYSTEM: Final[str] = """\
You judge whether one grocery item faithfully substitutes for another in a \
specific cooking context. You are not deciding whether a purchase should go \
ahead — you cannot see the price, the budget, or the payment authority, and \
they are not your concern.

Answer one question: if someone asked for the requested item and received the \
offered item, would their intent be satisfied?

- FAITHFUL — the offered item serves the same purpose. A cook would accept it.
- UNFAITHFUL — the offered item does not serve the same purpose, even if it is \
superficially similar.
- UNSURE — it genuinely depends on the dish, the cook, or information you do \
not have.

Use UNSURE when it is the truthful answer. Something downstream is built to \
handle not knowing; a confident guess here cannot be told apart from a fact \
later.

`score_bp` is fidelity in basis points, 0 to 10000. It should agree with your \
label: high for FAITHFUL, low for UNFAITHFUL, mid-range for UNSURE."""

OUTPUT_SCHEMA: Final[dict] = {
    "type": "object",
    "required": ["label", "score_bp", "rationale"],
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string", "enum": ["FAITHFUL", "UNFAITHFUL", "UNSURE"]},
        "score_bp": {"type": "integer", "minimum": 0, "maximum": 10000},
        "rationale": {"type": "string", "maxLength": 400},
    },
}

VERSION: Final[str] = "semantic-prompt-v1"

#: Opus 5. This runs on a handful of lines per order, and it is the one
#: judgment the deterministic layer could not make.
DEFAULT_MODEL = "claude-opus-5"


class ScoringError(RuntimeError):
    """A verdict could not be obtained or could not be understood."""


def build_question(goal: str, requested: RequestedItem, offered: CatalogItem) -> str:
    return (
        f"Cooking context: {goal}\n\n"
        f"Requested: {requested.raw_text} "
        f"(ingredient: {requested.base}, form: {requested.form})\n"
        f"Offered:   {offered.name} "
        f"(ingredient: {offered.base}, form: {offered.form})\n\n"
        f"Does the offered item preserve what was asked for?"
    )


def prompt_digest(goal: str, requested: RequestedItem, offered: CatalogItem) -> str:
    """Hash of everything that determined the model's input."""
    return canonical_hash(
        {
            "version": VERSION,
            "system": SYSTEM,
            "schema": OUTPUT_SCHEMA,
            "question": build_question(goal, requested, offered),
        }
    )


@runtime_checkable
class SemanticScorer(Protocol):
    """What Custodian requires of a substitution tie-breaker."""

    @property
    def model(self) -> str: ...

    def score(
        self, *, goal: str, requested: RequestedItem, offered: CatalogItem, cart_line_id: str
    ) -> SemanticVerdict: ...


def _verdict_from(
    payload: dict[str, Any], *, cart_line_id: str, requested_line_id: str,
    model: str, digest: str, raw: str,
) -> SemanticVerdict:
    try:
        return SemanticVerdict(
            cart_line_id=cart_line_id,
            requested_line_id=requested_line_id,
            label=VerdictLabel(payload["label"]),
            score_bp=int(payload["score_bp"]),
            model=model,
            prompt_digest=digest,
            raw_response=raw,
            obtained_at=utc_now(),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ScoringError(f"model output is not a usable verdict: {exc}") from exc


@dataclass
class RecordedScorer:
    """Replays recorded verdicts, keyed on the prompt digest.

    Not a stub — it runs the same validation path a live verdict does, so a
    change that breaks schema handling fails here rather than only against a
    live key.
    """

    responses: dict[str, str] = field(default_factory=dict)
    model_name: str = "recorded"

    @property
    def model(self) -> str:
        return self.model_name

    def record(self, goal: str, requested: RequestedItem, offered: CatalogItem,
               payload: dict) -> str:
        digest = prompt_digest(goal, requested, offered)
        self.responses[digest] = json.dumps(payload, sort_keys=True)
        return digest

    def score(self, *, goal: str, requested: RequestedItem, offered: CatalogItem,
              cart_line_id: str) -> SemanticVerdict:
        digest = prompt_digest(goal, requested, offered)
        if digest not in self.responses:
            raise ScoringError(
                f"no recorded verdict for this pair ({digest[:16]}…): "
                f"{requested.raw_text!r} -> {offered.name!r}"
            )
        raw = self.responses[digest]
        return _verdict_from(json.loads(raw), cart_line_id=cart_line_id,
                             requested_line_id=requested.line_id,
                             model=self.model_name, digest=digest, raw=raw)


@dataclass
class ClaudeScorer:
    """The live tie-breaker."""

    model_id: str = DEFAULT_MODEL
    effort: str = "medium"
    max_tokens: int = 2_048
    client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise ScoringError("the anthropic package is required for live scoring") from exc
            self.client = anthropic.Anthropic()

    @property
    def model(self) -> str:
        return self.model_id

    def score(self, *, goal: str, requested: RequestedItem, offered: CatalogItem,
              cart_line_id: str) -> SemanticVerdict:
        import anthropic

        question = build_question(goal, requested, offered)
        digest = prompt_digest(goal, requested, offered)
        try:
            response = self.client.messages.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": question}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
            )
        except anthropic.APIStatusError as exc:
            raise ScoringError(f"model returned {exc.status_code} while scoring") from exc
        except anthropic.APIConnectionError as exc:
            raise ScoringError(f"could not reach the model to score: {exc}") from exc

        if response.stop_reason == "refusal":
            raise ScoringError("model declined to score this substitution")

        raw = next((b.text for b in response.content if b.type == "text"), None)
        if not raw:
            raise ScoringError(f"model returned no text (stop_reason={response.stop_reason})")
        return _verdict_from(json.loads(raw), cart_line_id=cart_line_id,
                             requested_line_id=requested.line_id,
                             model=self.model_id, digest=digest, raw=raw)
