"""Offline tests for the web app bridge (model.py, llm.py)."""

import json

import numpy as np
import pandas as pd
import pytest

from scholarfund.finance import recommend_portfolio
from webapp import llm, model

rng = np.random.default_rng(0)
dates = pd.date_range("2016-01-31", periods=120, freq="ME")
RETURNS = pd.DataFrame({
    "BIL": rng.normal(0.003, 0.001, 120),
    "BND": rng.normal(0.004, 0.015, 120),
    "VTI": rng.normal(0.009, 0.045, 120),
    "VXUS": rng.normal(0.007, 0.050, 120),
    "BNDX": rng.normal(0.003, 0.012, 120),
}, index=dates)

SETTINGS = {"risk": "Growth", "ethics": "Standard", "pe": 20,
            "tax_on": True, "tax": 8.0, "payout": 3.0, "gift": 200_000,
            "years": 10, "infl": 2.5}


@pytest.fixture
def calls(monkeypatch):
    calls = []

    def fake_run_analysis(**inputs):
        calls.append(inputs)
        options = {k: v for k, v in inputs.items() if k != "ethical_policy"}
        result = recommend_portfolio(RETURNS, n_simulations=50, **options)
        result["sustainable_payouts"] = None
        result["data_context"] = {
            "market_data": {"n_months": 120}, "macro": {},
            "ethics": None, "generated_on": "2026-10-23",
        }
        return result

    monkeypatch.setattr(model, "run_analysis", fake_run_analysis)
    return calls


def test_settings_are_translated_for_the_engine(calls):
    model.run_scenario(SETTINGS)
    current, no_tax, more_pe = calls
    assert current["annual_payout"] == 6_000          # 3% of 200,000
    assert current["inflation_rate"] == pytest.approx(0.025)
    assert current["excise_tax_rate"] == pytest.approx(0.08)
    assert current["pe_share"] == pytest.approx(0.20)
    assert current["horizon_years"] == 10
    # Comparisons: tax switched off, and Harvard's 40% private equity.
    assert no_tax["excise_tax_rate"] == 0
    assert more_pe["pe_share"] == pytest.approx(0.40)


def test_tax_toggle_off_compares_with_harvard_tier(calls):
    model.run_scenario({**SETTINGS, "tax_on": False, "pe": 40})
    current, with_tax, less_pe = calls
    assert current["excise_tax_rate"] == 0
    assert with_tax["excise_tax_rate"] == pytest.approx(0.08)
    assert less_pe["pe_share"] == pytest.approx(0.20)


def test_allocation_adds_up_to_the_gift(calls):
    R = model.run_scenario(SETTINGS)
    assert R["shown_strategy"] == "Growth"
    assert sum(R["alloc"].values()) == pytest.approx(SETTINGS["gift"], abs=5)
    # 3% of 200,000 for 10 years, indexed on 2.5% inflation.
    assert R["total_promised"] == pytest.approx(
        sum(6_000 * 1.025 ** year for year in range(10))
    )


def test_context_is_valid_json_for_the_chat(calls):
    R = model.run_scenario(SETTINGS)
    context = json.loads(llm.build_context(SETTINGS, R))
    assert context["strategy_shown"] == "Growth"
    assert context["same_strategy_with_tax_at"]["tax_pct"] == 0
    assert context["same_strategy_with_private_equity_at"]["pe_pct"] == 40
    assert "engine_results" in context


def test_actions_are_parsed_and_clamped():
    text, action = llm.split_action(
        'Done.\nACTION: {"risk": "Growth", "ethics": "Strict", "payout": 12, '
        '"infl": -1, "years": 100, "gift": 5, "pe": 40, "tax_on": false, '
        '"tax": 25}'
    )
    assert text == "Done."
    assert llm.sanitize(action) == {
        "risk": "Growth", "ethics": "Strict", "payout": 8.0,
        "infl": 0.0, "years": 40, "gift": 10_000, "pe": 40,
        "tax_on": False, "tax": 10.0,
    }


def test_unknown_values_are_ignored():
    assert llm.sanitize(
        {"risk": "YOLO", "ethics": "Lax", "pe": 35, "tax_on": "yes"}
    ) == {}
