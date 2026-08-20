"""Place a messy product name into ``(base, form, category)``.

This is the primitive the substitution scorer rests on (ADR-007). Lexical
overlap cannot separate "coconut milk -> coconut cream" from
"coconut milk -> almond milk" — both score 0.3333 on Jaccard. Decomposing into
base identity and form makes the first a listed form pair and the second a base
change, and both resolve deterministically.

Transliteration is folded into the alias lists rather than handled as a separate
pass. "doodh" and "milk" are two spellings of one identity, so they belong on
one entry; a separate translit layer would be a second lookup that could
disagree with the first.

An unplaceable name yields ``base=UNKNOWN``. That is a real answer, not a
failure: an unknown base escalates rather than guessing, which is where
calibrated abstention comes from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Self

import yaml

from custodian.ingest.text import remove_phrases, strip_punctuation
from custodian.ingest.units import Measure, find_measure
from custodian.schemas.catalog import UNKNOWN

DEFAULT_LEXICON_DIR: Final[Path] = Path(__file__).resolve().parents[3] / "data" / "lexicon"


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a product name landed in the taxonomy."""

    base: str
    form: str
    category: str
    #: The pack size found in the name, if any.
    measure: Measure | None
    #: What remained after brands, filler, price and pack size were removed.
    residue: str

    @property
    def resolved(self) -> bool:
        return self.base != UNKNOWN


class TaxonomyError(RuntimeError):
    """Raised when the lexicon files are unusable."""


class Taxonomy:
    """The hand-authored lexicon, loaded and queryable."""

    def __init__(self, taxonomy: dict, compatibility: dict) -> None:
        self.version: str = taxonomy["version"]
        self.compatibility_version: str = compatibility["version"]

        self._categories: dict[str, str] = {}
        self._default_forms: dict[str, str] = {}
        base_aliases: list[tuple[str, str]] = []
        for base, spec in taxonomy["bases"].items():
            self._categories[base] = spec["category"]
            self._default_forms[base] = spec.get("default_form", UNKNOWN)
            base_aliases += [(alias.lower(), base) for alias in spec["aliases"]]

        form_aliases: list[tuple[str, str]] = []
        for form, aliases in taxonomy["forms"].items():
            form_aliases += [(alias.lower(), form) for alias in aliases]

        # Longest alias first: "kali mirch" must win over "mirch", and
        # "garam masala" over "gram".
        self._base_aliases = sorted(base_aliases, key=lambda pair: -len(pair[0]))
        self._form_aliases = sorted(form_aliases, key=lambda pair: -len(pair[0]))

        self._rules: dict[tuple[str, str], str] = {
            (rule["base"], rule["form"]): rule["category"]
            for rule in taxonomy.get("category_rules", [])
        }

        self._filler: frozenset[str] = frozenset(
            phrase.strip().lower()
            for group in ("brands", "noise")
            for line in taxonomy.get(group, [])
            for phrase in str(line).split(",")
            if phrase.strip()
        )

        self._base_scores: dict[tuple[str, str], int] = {}
        self._base_notes: dict[tuple[str, str], str] = {}
        for pair in taxonomy.get("base_equivalence", []):
            a, b = pair["bases"]
            key = tuple(sorted((a, b)))
            self._base_scores[key] = int(pair["score_bp"])
            self._base_notes[key] = pair.get("note", "")

        self._form_scores: dict[tuple[str, str], int] = {}
        self._form_notes: dict[tuple[str, str], str] = {}
        for pair in compatibility["pairs"]:
            a, b = pair["forms"]
            key = tuple(sorted((a, b)))
            self._form_scores[key] = int(pair["score_bp"])
            self._form_notes[key] = pair.get("note", "")

    @classmethod
    def load(cls, directory: Path | str = DEFAULT_LEXICON_DIR) -> Self:
        """Load the lexicon from disk."""
        directory = Path(directory)
        try:
            taxonomy = yaml.safe_load((directory / "taxonomy.yaml").read_text(encoding="utf-8"))
            compatibility = yaml.safe_load(
                (directory / "form_compatibility.yaml").read_text(encoding="utf-8")
            )
        except OSError as exc:
            raise TaxonomyError(f"cannot read lexicon from {directory}: {exc}") from exc
        return cls(taxonomy, compatibility)

    # --- placement ---------------------------------------------------------

    def place(self, name: str) -> Placement:
        """Reduce a product name to base, form and category."""
        measure = None
        text = strip_punctuation((name or "").lower())

        if (found := find_measure(text)) is not None:
            measure, text = found
        text = remove_phrases(text, self._filler)
        residue = re.sub(r"\s+", " ", text).strip()

        form_hits = self._match(residue, self._form_aliases)
        base_hits = self._match(residue, self._base_aliases)

        base, form = self._disambiguate(base_hits, form_hits)
        category = self._categorise(base, form)
        return Placement(base=base, form=form, category=category, measure=measure, residue=residue)

    @staticmethod
    def _match(text: str, aliases: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Every alias present as a whole word, longest first, no overlaps."""
        hits: list[tuple[str, str]] = []
        consumed = text
        for alias, key in aliases:
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, consumed):
                hits.append((alias, key))
                consumed = re.sub(pattern, " ", consumed)
        return hits

    def _disambiguate(
        self, base_hits: list[tuple[str, str]], form_hits: list[tuple[str, str]]
    ) -> tuple[str, str]:
        """Decide which hit is the identity and which is the shape.

        "milk" is both a base (dairy milk) and a form (coconut milk). When a
        distinct base is also present, the shared token is the form; when it is
        the only base, it is the base and takes its default form.
        """
        form_aliases = {alias for alias, _ in form_hits}
        distinct = [(alias, key) for alias, key in base_hits if alias not in form_aliases]

        if len(distinct) > 1:
            # "coconut almond blend" — two candidate identities, no way to pick.
            # UNKNOWN escalates, which is the correct answer to an ambiguity.
            return UNKNOWN, UNKNOWN
        if distinct:
            base = distinct[0][1]
            form = form_hits[0][1] if form_hits else self._default_forms.get(base, UNKNOWN)
            return base, form
        if base_hits:
            base = base_hits[0][1]
            return base, self._default_forms.get(base, UNKNOWN)
        return UNKNOWN, form_hits[0][1] if form_hits else UNKNOWN

    def _categorise(self, base: str, form: str) -> str:
        if base == UNKNOWN:
            return UNKNOWN
        return self._rules.get((base, form)) or self._categories.get(base, UNKNOWN)

    # --- form compatibility ------------------------------------------------

    def form_compatibility(self, left: str, right: str) -> int | None:
        """Substitution score for two forms of the same base, in basis points.

        ``None`` means the pair is not in the table — which escalates. An
        unlisted pair is one we have not judged, not one we judged badly, and
        collapsing that distinction is how a gate becomes confidently wrong.
        """
        if left == right:
            return 10_000
        if UNKNOWN in (left, right):
            return None
        return self._form_scores.get(tuple(sorted((left, right))))

    def base_compatibility(self, left: str, right: str) -> int | None:
        """Substitution score for two *identities*, in basis points.

        Kept apart from ``form_compatibility`` because the two answer different
        questions. Coconut milk to coconut cream is one ingredient in another
        shape; sunflower oil to groundnut oil is a different ingredient serving
        the same purpose. A single table would let a form rule authorise an
        identity change, which is exactly the mistake ADR-007 exists to prevent.

        ``None`` means these identities have no recorded relationship — the
        default answer for a base change, and the reason ``SUBST_BASE_CHANGED``
        can reject deterministically.
        """
        if left == right:
            return 10_000
        if UNKNOWN in (left, right):
            return None
        return self._base_scores.get(tuple(sorted((left, right))))

    def compatibility_note(self, left: str, right: str) -> str:
        key = tuple(sorted((left, right)))
        return self._form_notes.get(key) or self._base_notes.get(key, "")

    def category_of(self, base: str) -> str:
        return self._categories.get(base, UNKNOWN)

    @property
    def lexicon_version(self) -> str:
        """Composite version recorded in every snapshot."""
        return f"{self.version}+{self.compatibility_version}"


@lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    """The shipped lexicon, loaded once."""
    return Taxonomy.load()
