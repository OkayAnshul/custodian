"""Attribute decomposition: the primitive ADR-007 replaced lexical similarity with."""

import pytest

from custodian.ingest.taxonomy import Taxonomy, default_taxonomy
from custodian.ingest.units import Measure, Unit
from custodian.schemas.catalog import UNKNOWN


@pytest.fixture(scope="module")
def tax() -> Taxonomy:
    return default_taxonomy()


# --- the case §6's primitive cannot decide ---------------------------------

def test_jaccard_cannot_separate_the_flagship_pair():
    """The premise of ADR-007, asserted rather than claimed in a document."""
    def jaccard(a: str, b: str) -> float:
        x, y = set(a.split()), set(b.split())
        return len(x & y) / len(x | y)

    faithful = jaccard("coconut milk", "coconut cream")
    unfaithful = jaccard("coconut milk", "almond milk")
    assert faithful == unfaithful == pytest.approx(1 / 3)


def test_attribute_decomposition_separates_it_deterministically(tax):
    milk, cream, almond = (tax.place(n) for n in ("Coconut Milk 400ml", "Coconut Cream 200ml", "Almond Milk 1L"))

    # Faithful: same base, a listed form pair.
    assert milk.base == cream.base == "coconut"
    assert tax.form_compatibility(milk.form, cream.form) == 8_500

    # Unfaithful: the base changed, and these two identities have no relationship.
    assert almond.base == "almond" != milk.base
    assert tax.base_compatibility(milk.base, almond.base) is None


# --- placement -------------------------------------------------------------

@pytest.mark.parametrize(
    "name,base,form,category",
    [
        ("Dabur Coconut Milk 400ml", "coconut", "milk", "dairy-alt"),
        ("Coconut Oil 500ml", "coconut", "oil", "cooking-oil"),
        ("Desiccated Coconut 100g", "coconut", "flakes", "baking"),
        ("Aashirvaad Select Sharbati Atta 5kg", "wheat", "flour", "staples"),
        ("Tata Namak 1kg", "salt", "whole", "staples"),
        ("pav kilo chawal", "rice", "whole", "staples"),
        ("Everest Haldi Powder 100gm", "turmeric", "powder", "spices"),
        ("Sabut Kali Mirch 50g", "black-pepper", "whole", "spices"),
        ("MDH Garam Masala 100 gm", "garam-masala", "powder", "spices"),
        ("toor dal 1kg", "pigeon-pea", "whole", "pulses"),
        ("dahi 400gm", "curd", "curd", "dairy"),
        ("fresh adrak 250gm", "ginger", "fresh", "produce"),
        ("Thai Red Curry Paste 200g", "thai-curry", "paste", "condiments"),
    ],
)
def test_places_real_merchant_names(tax, name, base, form, category):
    placement = tax.place(name)
    assert (placement.base, placement.form, placement.category) == (base, form, category)


def test_transliteration_is_folded_into_identity_not_a_second_lookup(tax):
    """doodh and milk are one identity, so they resolve to one base."""
    assert tax.place("doodh 500ml").base == tax.place("milk 500ml").base == "milk"
    assert tax.place("haldi 100g").base == tax.place("turmeric 100g").base == "turmeric"
    assert tax.place("pyaz 1kg").base == tax.place("onion 1kg").base == "onion"


def test_a_shared_token_is_the_form_when_a_distinct_base_is_present(tax):
    """`milk` is both a base and a form. Context decides which."""
    assert tax.place("Amul Taaza Milk 500ml").base == "milk"      # only candidate
    assert tax.place("Coconut Milk 400ml").base == "coconut"      # coconut is distinct
    assert tax.place("Coconut Milk 400ml").form == "milk"


def test_longest_alias_wins(tax):
    """`kali mirch` must beat `mirch`, `garam masala` must beat `gram`."""
    assert tax.place("Sabut Kali Mirch 50g").base == "black-pepper"
    assert tax.place("Lal Mirch Powder 100g").base == "chilli"
    assert tax.place("MDH Garam Masala 100 gm").base == "garam-masala"


def test_brands_and_marketing_filler_are_stripped(tax):
    assert tax.place("Aashirvaad Select Premium Sharbati Atta 5kg").base == "wheat"
    assert tax.place("atta 5kg").base == "wheat"


def test_category_depends_on_base_and_form_not_base_alone(tax):
    """Coconut milk is a dairy alternative; coconut oil is a cooking oil."""
    assert tax.place("Coconut Milk 400ml").category == "dairy-alt"
    assert tax.place("Coconut Oil 500ml").category == "cooking-oil"
    assert tax.place("Desiccated Coconut 100g").category == "baking"


def test_the_pack_size_comes_back_with_the_placement(tax):
    assert tax.place("Dabur Honey 250gm").measure == Measure(250, Unit.GRAM)
    assert tax.place("Kadhai 30cm").measure is None


# --- abstention ------------------------------------------------------------

def test_an_unplaceable_name_is_unknown_rather_than_guessed(tax):
    """UNKNOWN escalates. That is where calibrated abstention comes from."""
    placement = tax.place("Sparkle Glitter Pens 5 nos")
    assert placement.base == UNKNOWN
    assert not placement.resolved


def test_two_candidate_identities_resolve_to_unknown(tax):
    """An ambiguity has no right answer, so the honest output is no answer."""
    assert tax.place("coconut almond blend 200g").base == UNKNOWN


def test_an_unknown_base_never_scores_as_compatible(tax):
    assert tax.base_compatibility(UNKNOWN, "coconut") is None
    assert tax.form_compatibility(UNKNOWN, "milk") is None


# --- compatibility tables --------------------------------------------------

def test_identical_attributes_score_full(tax):
    assert tax.form_compatibility("milk", "milk") == 10_000
    assert tax.base_compatibility("coconut", "coconut") == 10_000


def test_compatibility_is_symmetric(tax):
    assert tax.form_compatibility("milk", "cream") == tax.form_compatibility("cream", "milk")
    assert tax.base_compatibility("butter", "ghee") == tax.base_compatibility("ghee", "butter")


def test_an_unlisted_pair_escalates_rather_than_scoring_zero(tax):
    """Not judged is not the same as judged badly."""
    assert tax.form_compatibility("milk", "oil") is None
    assert tax.base_compatibility("coconut", "almond") is None


def test_base_equivalence_is_a_separate_table_from_form_compatibility(tax):
    """A form rule must never be able to authorise an identity change."""
    assert tax.base_compatibility("sunflower", "groundnut") == 8_000  # identity swap
    assert tax.form_compatibility("sunflower", "groundnut") is None   # not a form question


def test_every_compatibility_entry_carries_a_stated_judgment(tax):
    assert tax.compatibility_note("milk", "cream")
    assert tax.compatibility_note("wheat", "refined-wheat")


def test_the_lexicon_version_travels_with_every_snapshot(tax):
    assert tax.lexicon_version == f"{tax.version}+{tax.compatibility_version}"
