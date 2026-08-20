"""The model's answer, recorded as evidence.

This is the hinge that makes ADR-010 work. When deterministic logic cannot
settle a substitution, an LLM is asked — once, with a constrained schema — and
what it returned is written to the ledger as an *observation*, with the same
standing as a catalog price or a gateway response.

``decide()`` then reads that recorded verdict. It never calls a model, which is
why a decision replays byte-identically without one. The model genuinely
participates; it simply is not consulted twice, and it is not the authority.

``prompt_digest`` and ``raw_response`` are what make that auditable. Without
them "the model said faithful" is an assertion; with them, a reviewer can see
exactly what was asked and exactly what came back.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from custodian.schemas.types import Contract, Digest, Identifier, ScoreBp, Timestamp


class VerdictLabel(StrEnum):
    """The only three answers the model is allowed to give.

    ``UNSURE`` exists so the model has somewhere honest to go. A schema with
    only two options manufactures false confidence, and a confidently wrong
    gate is worse than one that asks.
    """

    FAITHFUL = "FAITHFUL"
    UNFAITHFUL = "UNFAITHFUL"
    UNSURE = "UNSURE"


class SemanticVerdict(Contract):
    """One escalated substitution, and what came back."""

    cart_line_id: Identifier
    requested_line_id: Identifier

    label: VerdictLabel
    #: The model's fidelity score. Scored by the model, weighed by the gate.
    score_bp: ScoreBp

    #: Provenance. A verdict whose origin cannot be established is not evidence.
    model: str = Field(min_length=1, max_length=128)
    prompt_digest: Digest
    raw_response: str = Field(max_length=8_192)
    obtained_at: Timestamp

    @property
    def usable(self) -> bool:
        """Whether this verdict settles anything. ``UNSURE`` does not."""
        return self.label is not VerdictLabel.UNSURE
