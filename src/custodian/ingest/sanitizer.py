"""Sanitize merchant-authored copy on the way in.

This is where the attack surface is. The catalog half of Custodian exists to
make a merchant sellable to agents, and the moment merchant text enters an
agent's context, whoever writes that text can address the agent directly. The
merchant may not even be the author — marketplace listings, supplier feeds and
scraped descriptions all end up in the same column.

Rules only, no model. Ingest runs over every item on every refresh, so the check
must be cheap; and a classifier trained on our own adversarial fixtures and
evaluated on the same corpus would be circular. This also keeps the claim in §6
literally true: the LLM occupies exactly two positions, and this is not one.

The design point that matters: flagged spans are **kept**, not merely removed.
``clean_text`` is what reaches the agent; ``flagged_spans`` is what was taken
out, recorded in the snapshot and therefore in the ledger. A dispute needs to
show that something was stripped, not merely that the feed looked fine
afterwards.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from custodian.schemas.catalog import Sanitization, SanitizerFlag

#: Text addressed to a reader that follows instructions. Merchant copy describes
#: a product; it does not tell anyone what to do about it.
_INSTRUCTION: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|above)\b",
        r"\bdisregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|instructions?)\b",
        r"\b(?:new|updated|revised)\s+instructions?\b",
        r"^\s*(?:system|assistant|user|developer)\s*:",
        r"<\s*/?\s*(?:system|assistant|instructions?)\s*>",
        # NOTE: a bare "you must/should" pattern was tried and removed. It flags
        # "You must try this with fresh coriander!" — ordinary marketing copy —
        # and suppressing a legitimate product's whole description is a real cost
        # to the merchant. Every attack it caught is already covered by the
        # action-specific patterns below, so it added false positives and no
        # coverage. False-positive cost is graded in BENIGN_LOOKALIKES.
        r"\b(?:add|append|include)\s+(?:this|it|the\s+following)\s+to\s+(?:the\s+)?cart\b",
        r"\b(?:approve|authorise|authorize|confirm)\s+(?:this|the)\s+(?:order|purchase|payment|transaction)\b",
        r"\b(?:do\s+not|don't|never)\s+(?:verify|check|validate|question)\b",
        r"\boverride\s+(?:the\s+)?(?:budget|limit|policy|constraint|check)\b",
        r"\b(?:skip|bypass)\s+(?:the\s+)?(?:verification|validation|check|gate)\b",
        r"\bact\s+as\b|\bpretend\s+(?:to\s+be|you)\b",
    )
)

#: Characters that render as nothing. Legitimate product copy has no use for them.
_INVISIBLE: Final[re.Pattern[str]] = re.compile(r"[​-‏⁠-⁤﻿­]")

#: Bidirectional overrides, which can make displayed text differ from stored text.
_BIDI: Final[re.Pattern[str]] = re.compile(r"[‪-‮⁦-⁩]")

_HTML_COMMENT: Final[re.Pattern[str]] = re.compile(r"<!--.*?-->", re.DOTALL)
_HIDDEN_STYLE: Final[re.Pattern[str]] = re.compile(
    r"<[^>]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)[^>]*>", re.IGNORECASE
)

#: Long unbroken base64-ish runs, and escape sequences.
_ENCODED: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
    re.compile(r"(?:\\u[0-9a-fA-F]{4}){4,}"),
    re.compile(r"(?:%[0-9a-fA-F]{2}){8,}"),
)

#: Copy asserting its own price. The price field is the price; prose that
#: restates it is either redundant or an attempt to be believed instead.
_PRICE_CLAIM: Final[re.Pattern[str]] = re.compile(
    r"\b(?:actual|real|true|correct|final|discounted)\s+price\s+(?:is|:)\s*"
    r"(?:₹|rs\.?|inr)?\s*[\d,]+|"
    r"\bprice\s+(?:is|:)\s*(?:₹|rs\.?|inr)\s*[\d,]+|"
    r"\bcharge\s+(?:only\s+)?(?:₹|rs\.?|inr)\s*[\d,]+",
    re.IGNORECASE,
)


#: Flags whose presence suppresses the whole field rather than editing it.
#:
#: Excising matched spans and keeping the remainder is not safe against a
#: crafted payload: an attacker who knows the patterns can write text whose
#: *surviving* fragment carries the meaning. Partial cleaning also produces
#: incoherent copy — "Great honey. instructions and ." — which is worse for the
#: agent than no description at all. An item with a suppressed description is
#: still perfectly sellable: it keeps its name, price and stock.
_SUPPRESSING: Final[frozenset[SanitizerFlag]] = frozenset({
    SanitizerFlag.INSTRUCTION_LIKE,
    SanitizerFlag.ENCODED_PAYLOAD,
})


@dataclass(frozen=True, slots=True)
class SanitizerResult:
    """What reaches the agent, and what was taken out of it."""

    clean_text: str
    finding: Sanitization
    #: True when the field was dropped whole rather than edited.
    suppressed: bool = False

    @property
    def clean(self) -> bool:
        return self.finding.clean


def sanitize(text: str) -> SanitizerResult:
    """Strip agent-directed content from merchant copy, keeping the evidence."""
    if not text:
        return SanitizerResult(clean_text="", finding=Sanitization())

    flags: list[SanitizerFlag] = []
    spans: list[str] = []
    working = text

    def strip(pattern: re.Pattern[str], flag: SanitizerFlag) -> None:
        nonlocal working
        if found := pattern.findall(working):
            flags.append(flag)
            spans.extend(_describe(match) for match in found)
            working = pattern.sub(" ", working)

    # Structural hiding first: an HTML comment may contain an instruction, and
    # removing the wrapper before scanning would let the instruction escape
    # unflagged — or removing the instruction first would leave a hollow comment.
    for pattern in (_HTML_COMMENT, _HIDDEN_STYLE):
        strip(pattern, SanitizerFlag.HIDDEN_TEXT)
    if _INVISIBLE.search(working):
        if SanitizerFlag.HIDDEN_TEXT not in flags:
            flags.append(SanitizerFlag.HIDDEN_TEXT)
        spans.append(f"{len(_INVISIBLE.findall(working))} invisible character(s)")
        working = _INVISIBLE.sub("", working)
    if _BIDI.search(working):
        flags.append(SanitizerFlag.DIRECTION_OVERRIDE)
        spans.append(f"{len(_BIDI.findall(working))} bidirectional override(s)")
        working = _BIDI.sub("", working)

    for pattern in _ENCODED:
        strip(pattern, SanitizerFlag.ENCODED_PAYLOAD)
    for pattern in _INSTRUCTION:
        strip(pattern, SanitizerFlag.INSTRUCTION_LIKE)
    strip(_PRICE_CLAIM, SanitizerFlag.PRICE_CLAIM)

    working = unicodedata.normalize("NFKC", working)
    suppressed = bool(_SUPPRESSING.intersection(flags))
    return SanitizerResult(
        clean_text="" if suppressed else re.sub(r"\s+", " ", working).strip(),
        finding=Sanitization(
            flags=tuple(dict.fromkeys(flags)),      # de-duplicated, order preserved
            flagged_spans=tuple(dict.fromkeys(spans))[:16],
        ),
        suppressed=suppressed,
    )


def _describe(match: str | tuple[str, ...]) -> str:
    """Render a regex hit as one evidence string, truncated."""
    text = match if isinstance(match, str) else next((part for part in match if part), "")
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:160] + ("…" if len(collapsed) > 160 else "")


def flag_price_claim(finding: Sanitization) -> Sanitization:
    """Add a price-claim flag to an existing finding, preserving its spans."""
    if SanitizerFlag.PRICE_CLAIM in finding.flags:
        return finding
    return Sanitization(
        flags=finding.flags + (SanitizerFlag.PRICE_CLAIM,),
        flagged_spans=finding.flagged_spans,
    )
