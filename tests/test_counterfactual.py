"""The money figures. These get quoted, so they get tested."""

import pytest

from custodian import bp
from eval.counterfactual import measure, transactability
from eval.corpus.schema import Split


@pytest.fixture(scope="module")
def measured():
    return measure()


@pytest.fixture(scope="module")
def reach():
    return transactability()


# --- internal consistency --------------------------------------------------

def test_every_order_lands_on_exactly_one_side(measured):
    """Settled plus stopped is the whole corpus at catalog prices."""
    assert measured.orders == 120
    assert measured.settled_paise > 0 and measured.wrong_money_stopped_paise > 0


def test_the_forgery_figure_is_the_gap_between_claim_and_catalog(measured):
    """The agent's asserted total is lower than the real one by exactly this."""
    real = measured.settled_paise + measured.wrong_money_stopped_paise
    assert measured.unchecked_paise + measured.forged_amount_paise == real


def test_most_of_the_corpus_value_is_stopped(measured):
    """A corpus where almost nothing is refused would not be testing much."""
    assert 5_000 < measured.stopped_share_bp < 9_500


def test_the_saving_is_reported_with_its_cost(measured):
    """A number quoted without its friction is advertising."""
    assert measured.clean_orders == 60
    assert measured.clean_orders_held == 0
    assert measured.friction_bp == 0


def test_unrequested_items_are_a_material_share(measured):
    """Scope creep is the failure a budget check cannot see, so it must be sized."""
    assert measured.unrequested_paise > 0
    assert measured.unrequested_paise < measured.wrong_money_stopped_paise


def test_adversarial_money_is_a_subset_of_money_stopped(measured):
    assert 0 < measured.adversarial_stopped_paise <= measured.wrong_money_stopped_paise


def test_most_orders_never_reach_a_model(measured):
    assert measured.orders_reaching_a_model < measured.orders // 3


def test_the_model_cost_is_reported_per_line_because_that_is_how_it_is_charged(measured):
    """A model is paid per question asked, not per order placed.

    The README quotes the per-line figure, so the per-line figure is what the
    tool prints. Every escalating line sits inside an escalating order, which is
    why these two counts can be equal and can never cross.
    """
    assert measured.cart_lines == 162
    assert measured.lines_reaching_a_model == 24
    assert measured.lines_reaching_a_model >= measured.orders_reaching_a_model
    assert measured.model_line_share_bp == 1481


# --- the split ------------------------------------------------------------

def test_the_test_split_is_measured_separately():
    """Headline figures are reported on TEST; tuning happens on DEV."""
    dev, test = measure(Split.DEV), measure(Split.TEST)
    assert dev.orders + test.orders == 120
    assert test.wrong_money_stopped_paise > 0


# --- transactability -------------------------------------------------------

def test_ingest_makes_the_catalog_buyable_from(reach):
    """The growth claim, measured rather than asserted."""
    assert reach["rows"] == 70
    assert reach["raw_all"] < 20          # a raw export is mostly unusable to an agent
    assert reach["placed"] >= 69          # after ingest, nearly all of it works
    assert reach["placed"] > reach["raw_all"] * 3


def test_each_criterion_is_reported_separately(reach):
    """So the claim can be checked rather than taken on trust."""
    for key in ("raw_priced", "raw_categorised", "raw_stock", "raw_sized"):
        assert key in reach
    assert reach["raw_all"] <= min(reach["raw_priced"], reach["raw_categorised"],
                                   reach["raw_stock"])


def test_pack_size_is_never_a_column_in_the_raw_export(reach):
    """It lives inside the product name, which is why normalisation is needed."""
    assert reach["raw_sized"] == 0
    assert reach["sized"] > 60
