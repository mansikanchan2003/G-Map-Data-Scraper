"""
What a campaign costs.

Meta bills per delivered message at a rate that depends on the template's
category, and the gap between the two categories is large enough that getting
it wrong misstates a bill several times over. These tests pin the arithmetic
and the fallback.
"""
from decimal import Decimal

import pytest

from src.services import pricing


def test_marketing_and_utility_are_priced_apart():
    """The whole reason the category is a choice in the UI."""
    marketing = pricing.estimate("MARKETING", 1000)
    utility = pricing.estimate("UTILITY", 1000)

    assert marketing["net"] == 863.10
    assert utility["net"] == 115.00
    # Roughly 7.5x, which is what makes filing a transactional template as
    # marketing an expensive mistake.
    assert marketing["net"] > utility["net"] * 7


def test_gst_is_added_on_top():
    out = pricing.estimate("MARKETING", 100)

    assert out["net"] == 86.31
    assert out["gst"] == 15.54          # 18% of 86.31
    assert out["total"] == 101.85
    assert out["currency"] == "INR"


def test_an_unknown_category_is_priced_as_marketing():
    """
    The expensive assumption on purpose: a cost that surprises downwards is
    better than one that surprises upwards.
    """
    assert pricing.estimate(None, 10)["net"] == pricing.estimate("MARKETING", 10)["net"]
    assert pricing.estimate("", 10)["net"] == pricing.estimate("MARKETING", 10)["net"]
    assert pricing.estimate("WEIRD", 10)["net"] == pricing.estimate("MARKETING", 10)["net"]


def test_category_matching_ignores_case():
    assert pricing.rate_for("utility") == pricing.rate_for("UTILITY")


@pytest.mark.parametrize("delivered", [0, None, -5])
def test_nothing_delivered_costs_nothing(delivered):
    out = pricing.estimate("MARKETING", delivered)

    assert out["billable_messages"] == 0
    assert out["net"] == 0.0
    assert out["total"] == 0.0


def test_the_real_september_bill_is_reproduced():
    """
    Meta billed 3,149 marketing messages at 2717.90 over the campaigns run in
    September. Reproducing that exactly is what says the rate card here still
    matches the one Meta is charging against.
    """
    out = pricing.estimate("MARKETING", 3149)

    assert out["net"] == 2717.90


def test_money_is_rounded_to_paise_not_truncated():
    # 3 x 0.8631 = 2.5893, which rounds up rather than down.
    assert pricing.estimate("MARKETING", 3)["net"] == 2.59


def test_rates_are_exact_decimals():
    """
    Float arithmetic over thousands of messages drifts. The rates are
    Decimals so the total is exact before it is rounded once, at the end.
    """
    assert all(isinstance(v, Decimal) for v in pricing.RATES_INR.values())
