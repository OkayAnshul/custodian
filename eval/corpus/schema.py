"""The evaluation corpus: cases, expectations, and where each label came from.

Label provenance is a field, not a footnote. Three classes have ground truth
that follows from the definition — a forged price *is* a rejection, a clean cart
*is* an approval, an unresolvable substitution *is* a hold — and those labels are
marked ``DERIVED``. The benign-divergence class does not work that way: whether
coconut cream is an acceptable stand-in for coconut milk is a judgment about
cooking, and it is the class the project's difficulty actually lives in.

Those labels are marked ``PROPOSED`` until a human signs them off, and the
harness reports them separately. This is not bookkeeping. If the same model that
writes the tie-break prompt also writes the graded ground truth it is scored
against, the evaluation is circular, and a reviewer is entitled to check which
numbers rest on that.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from custodian.gate.reasons import ReasonCode
from custodian.schemas.decision import Outcome
from custodian.schemas.intent import SubstitutionPolicy
from custodian.schemas.types import Contract, Identifier, Paise, Quantity


class CaseClass(StrEnum):
    """The four classes from the problem statement's §7."""

    CLEAN = "CLEAN"
    BENIGN_DIVERGENCE = "BENIGN_DIVERGENCE"
    ADVERSARIAL = "ADVERSARIAL"
    AMBIGUOUS = "AMBIGUOUS"


class LabelSource(StrEnum):
    """Who is answerable for this case's expected outcome."""

    #: Follows mechanically from the case construction. A cart quoting a price
    #: the catalog does not have is a rejection by definition, not by opinion.
    DERIVED = "DERIVED"
    #: A human judged this case. The only source that counts for the
    #: benign-divergence numbers.
    HUMAN = "HUMAN"
    #: Machine-drafted and awaiting review. Reported separately and never folded
    #: into a headline figure.
    PROPOSED = "PROPOSED"


class Split(StrEnum):
    """Thresholds are chosen on DEV and reported on TEST. Never the same set."""

    DEV = "DEV"
    TEST = "TEST"


class RequestedSpec(Contract):
    raw_text: str = Field(min_length=1, max_length=256)
    quantity: Quantity = 1
    max_unit_price_paise: Paise | None = None


class CartSpec(Contract):
    item_id: Identifier
    quantity: Quantity = 1
    #: Overrides the catalog price, to model a forged or stale claim.
    asserted_price_paise: Paise | None = None
    satisfies: Identifier | None = None


class CatalogTweak(Contract):
    """A change to one catalog item, applied before the snapshot is built."""

    item_id: Identifier
    out_of_stock: bool = False
    #: Replaces the merchant's description. Adversarial cases put frozen
    #: injection strings here — inert data, graded against the sanitizer.
    description: str | None = None
    price_paise: Paise | None = None


class Expectation(Contract):
    """What the gate should do, and the least that must appear in its reasons."""

    outcome: Outcome
    #: Codes that must be present. A case asserting only the outcome passes for
    #: the wrong reason as easily as the right one.
    reason_codes: tuple[ReasonCode, ...] = ()
    #: Codes that must be absent — usually the ones a naive implementation
    #: would raise instead.
    forbidden_reason_codes: tuple[ReasonCode, ...] = ()


class Case(Contract):
    """One graded order."""

    case_id: Identifier
    case_class: CaseClass
    split: Split
    label_source: LabelSource

    goal: str = Field(min_length=1, max_length=512)
    budget_paise: Paise | None = None
    policy: SubstitutionPolicy = SubstitutionPolicy.SAME_BASE
    merchant_scope: tuple[Identifier, ...] = ("kirana-blr-001",)
    category_scope: tuple[str, ...] | None = None

    requested: tuple[RequestedSpec, ...]
    cart: tuple[CartSpec, ...]
    catalog_tweaks: tuple[CatalogTweak, ...] = ()

    #: Recorded verdicts for lines this case expects to escalate. Absent means
    #: the model was not asked, which is itself a case worth grading.
    verdicts: tuple[tuple[Identifier, str, int], ...] = ()

    expect: Expectation
    #: Why this is the right answer. Required — a case without a stated reason
    #: is a number nobody can check.
    rationale: str = Field(min_length=10, max_length=1_024)

    @model_validator(mode="after")
    def _judgment_classes_are_not_machine_labelled(self) -> "Case":
        if (
            self.case_class is CaseClass.BENIGN_DIVERGENCE
            and self.label_source is LabelSource.DERIVED
        ):
            raise ValueError(
                f"{self.case_id}: benign divergence cannot be DERIVED — whether a "
                "substitution is acceptable is a judgment, not a consequence of how "
                "the case was built. Use HUMAN once reviewed, PROPOSED until then."
            )
        return self


class Corpus(Contract):
    """The graded set."""

    version: str = Field(min_length=1, max_length=32)
    cases: tuple[Case, ...]

    @model_validator(mode="after")
    def _case_ids_are_unique(self) -> "Corpus":
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate case_id: {duplicates}")
        return self

    def of_class(self, case_class: CaseClass) -> tuple[Case, ...]:
        return tuple(c for c in self.cases if c.case_class is case_class)

    def of_split(self, split: Split) -> tuple[Case, ...]:
        return tuple(c for c in self.cases if c.split is split)

    def reviewed(self) -> tuple[Case, ...]:
        """Cases whose label a human is answerable for, or that need no judgment."""
        return tuple(c for c in self.cases if c.label_source is not LabelSource.PROPOSED)

    def awaiting_review(self) -> tuple[Case, ...]:
        return tuple(c for c in self.cases if c.label_source is LabelSource.PROPOSED)
