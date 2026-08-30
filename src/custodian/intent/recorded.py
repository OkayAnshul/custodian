"""An intent parser that replays recorded model responses.

Used by the test suite, the eval harness and offline demos. It is not a stub:
it runs the same ``resolve`` path a live parse does, so a change that breaks
structured-output handling fails here rather than only against a live key.

Keying on the prompt digest rather than on the goal string is deliberate — a
fixture recorded under a different prompt version will not silently satisfy a
request built from the current one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from custodian.clock import utc_now
from custodian.ingest.taxonomy import Taxonomy
from custodian.intent import prompt as prompt_module
from custodian.intent.parser import ParseError, ParseResult, decode, resolve


@dataclass
class RecordedParser:
    """Replays a fixture for each prompt digest."""

    #: prompt digest -> the exact JSON string the model returned.
    responses: dict[str, str] = field(default_factory=dict)
    model_name: str = "recorded"
    taxonomy: Taxonomy | None = None
    #: prompt digest -> the model that actually produced it. See RecordedScorer.
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_recordings(cls, path: Path | None = None,
                        taxonomy: Taxonomy | None = None) -> "RecordedParser":
        """Replay parses that were actually received."""
        from custodian.gate.semantic import load_recordings

        entries = load_recordings("intent", path)
        return cls(
            responses={d: e["raw_response"] for d, e in entries.items()},
            provenance={d: e["model"] for d, e in entries.items()},
            taxonomy=taxonomy,
        )

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def has_real_recordings(self) -> bool:
        return bool(self.provenance)

    def record(self, goal: str, payload: dict) -> str:
        """Register a response for ``goal``. Returns the digest it was filed under."""
        digest = prompt_module.prompt_digest(goal)
        self.responses[digest] = json.dumps(payload, sort_keys=True)
        return digest

    def parse(self, goal: str, *, intent_id: str) -> ParseResult:
        digest = prompt_module.prompt_digest(goal)
        if digest not in self.responses:
            raise ParseError(
                f"no recorded response for this prompt ({digest[:16]}…). "
                f"Either the goal or the prompt version changed since it was recorded."
            )
        raw = self.responses[digest]
        return ParseResult(
            intent=resolve(decode(raw), intent_id=intent_id, taxonomy=self.taxonomy),
            model=self.provenance.get(digest, self.model_name),
            prompt_digest=digest,
            raw_response=raw,
            obtained_at=utc_now(),
        )
