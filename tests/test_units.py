"""250gm, 1/4 kg and pav kilo are one quantity. A parsing problem, not a reasoning one."""

import pytest

from custodian.ingest.units import Measure, Unit, UnitError, find_measure, parse_measure, same_measure


@pytest.mark.parametrize(
    "written",
    ["250gm", "250 gm", "250g", "250 grams", "0.25 kg", "1/4 kg", "1/4kg",
     "¼ kg", "1⁄4 kg", "quarter kilo", "pav kilo", "paav kilo", "pao kilo", "PAV KILO"],
)
def test_every_spelling_of_a_quarter_kilo_is_the_same_quantity(written):
    assert parse_measure(written) == Measure(250, Unit.GRAM)


@pytest.mark.parametrize(
    "written,grams",
    [("aadha kilo", 500), ("adha kg", 500), ("half kilo", 500), ("½ kg", 500),
     ("dedh kg", 1500), ("derh kilo", 1500), ("sawa kg", 1250), ("paune kg", 750),
     ("dhai kilo", 2500), ("1kg", 1000), ("5 kg", 5000), ("¾ kg", 750)],
)
def test_transliterated_hindi_fractions(written, grams):
    """pav, aadha, dedh, sawa, paune. A generic normaliser has no entry for these."""
    assert parse_measure(written) == Measure(grams, Unit.GRAM)


@pytest.mark.parametrize(
    "written,ml",
    [("500ml", 500), ("500 ML", 500), ("1 ltr", 1000), ("1L", 1000), ("1.5 litre", 1500),
     ("2 liters", 2000), ("¾ litre", 750), ("aadha litre", 500)],
)
def test_volume(written, ml):
    assert parse_measure(written) == Measure(ml, Unit.MILLILITRE)


@pytest.mark.parametrize(
    "written,count",
    [("1 dozen", 12), ("6 pcs", 6), ("6 pieces", 6), ("do packet", 2), ("teen nos", 3),
     ("ek pkt", 1), ("chaar units", 4), ("2 dozen", 24)],
)
def test_counts(written, count):
    assert parse_measure(written) == Measure(count, Unit.PIECE)


def test_the_vulgar_fraction_trap():
    """NFKC rewrites ¼ to 1⁄4 with U+2044, not ASCII /. See BROKE.md 004."""
    import unicodedata
    assert unicodedata.normalize("NFKC", "¼") == "1⁄4"
    assert parse_measure("¼ kg") == Measure(250, Unit.GRAM)  # not 4000


def test_find_measure_returns_the_name_without_the_pack_size():
    """The remainder is what the taxonomy classifies; a stray 500 is not a base."""
    measure, remainder = find_measure("Aashirvaad Select Atta 5kg")
    assert measure == Measure(5_000, Unit.GRAM)
    assert remainder == "Aashirvaad Select Atta"


def test_find_measure_is_none_when_there_is_none():
    assert find_measure("Kadhai 30cm") is None
    assert find_measure("") is None


@pytest.mark.parametrize("bad", ["Kadhai", "no numbers here", "0 kg", "0/4 kg"])
def test_unparseable_measures_raise_rather_than_guess(bad):
    with pytest.raises(UnitError):
        parse_measure(bad)


def test_division_by_zero_is_refused():
    with pytest.raises(UnitError):
        parse_measure("1/0 kg")


def test_same_measure_compares_quantities_not_spellings():
    assert same_measure("250gm", "pav kilo")
    assert same_measure("1 ltr", "1000 ml")
    assert not same_measure("250gm", "aadha kilo")


def test_units_do_not_cross():
    assert parse_measure("500 g") != parse_measure("500 ml")


def test_quantities_are_integers_so_a_pack_size_has_one_representation():
    assert isinstance(parse_measure("1/3 kg").quantity, int)
    assert parse_measure("1/3 kg") == Measure(333, Unit.GRAM)  # half-up, deterministic
