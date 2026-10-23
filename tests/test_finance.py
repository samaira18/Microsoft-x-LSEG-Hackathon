import numpy as np
import pandas as pd
import pytest

from scholarfund import finance
from scholarfund.finance import (
    BOND_SHARE,
    MIN_CLASS_SHARE,
    PE_LABEL,
    PE_SHARE,
    _sell,
    calculate_reserve_amount,
    portfolio_stress_shock,
    recommend_portfolio,
    simulate_payouts,
)

# Synthetic test data ONLY — not actual historical market data.
rng = np.random.default_rng(42)
dates = pd.date_range("2016-01-31", periods=120, freq="ME")

ASSET_RETURNS = pd.DataFrame({
    "BIL": rng.normal(0.003, 0.001, 120),
    "BND": rng.normal(0.004, 0.015, 120),
    "BNDX": rng.normal(0.003, 0.012, 120),
    "VTI": rng.normal(0.009, 0.045, 120),
    "VXUS": rng.normal(0.007, 0.050, 120),
}, index=dates)


def run(**kwargs):
    params = {
        "asset_returns": ASSET_RETURNS,
        "risk_tolerance": "Growth",
        "n_simulations": 200,
    }
    params.update(kwargs)
    return recommend_portfolio(**params)


def metadata(policy, allowed):
    return {
        asset: {policy: asset in allowed} for asset in ASSET_RETURNS.columns
    }


# ---------- reserve and buckets ----------

def test_reserve_is_indexed_on_inflation():
    assert calculate_reserve_amount(5_000, 0.03, 2) == pytest.approx(10_150)

    result = run(annual_payout=5_000, inflation_rate=0.03)
    inputs = result["client_inputs"]
    assert inputs["reserve_amount"] == pytest.approx(10_150)
    assert inputs["public_capital"] == pytest.approx(80_000)


def buckets(n_months, cash=0.0, low_risk=0.0, growth=0.0, pe=0.0):
    return pd.DataFrame({
        "cash": cash,
        "low_risk": low_risk,
        "growth": growth,
        "pe": pe,
    }, index=dates[:n_months])


def allocation(reserve=None, low=25_000, growth=25_000, pe=0.0):
    if reserve is None:
        reserve = calculate_reserve_amount(5_000, 0.03, 2)
    return {"reserve": reserve, "low": low, "growth": growth, "pe": pe}


def simulate(bucket_returns, alloc=None, **options):
    return simulate_payouts(
        bucket_returns,
        alloc or allocation(),
        annual_payout=5_000,
        inflation_rate=0.03,
        **options,
    )


def test_payments_come_from_cash_and_reserve_is_refilled():
    sim = simulate(buckets(36))
    history = sim["history"]
    assert history["cash_payment"].sum() == pytest.approx(sim["total_paid"])
    assert history["low_risk_payment"].max() < 1e-6
    assert history["growth_payment"].max() < 1e-6
    # The reserve always covers the next 24 indexed payments.
    next_24 = sum(5_000 * 1.03 ** (m // 12) / 12 for m in range(36, 60))
    assert sim["ending_cash"] == pytest.approx(next_24)
    assert not sim["funding_failure"]


def test_growth_is_not_sold_in_drawdown():
    growth = [-0.40] + [0.0] * 35
    sim = simulate(buckets(36, growth=growth))
    history = sim["history"]
    assert history["growth_payment"].max() < 1e-6
    # Growth keeps its post-crash value: no refill, no rebalancing sale.
    assert history["growth_balance"].iloc[-1] == pytest.approx(25_000 * 0.6)
    assert sim["forced_growth_sales"] == 0
    assert not sim["funding_failure"]


def test_forced_sale_is_counted_when_nothing_else_is_left():
    growth = [-0.40] + [0.0] * 47
    sim = simulate(buckets(48, growth=growth), allocation(low=0.0))
    assert sim["forced_growth_sales"] > 0
    assert not sim["funding_failure"]


# ---------- excise tax on realized gains ----------

def test_sale_pays_tax_on_the_gain_only():
    value, basis, raised, tax = _sell(
        np.array([200.0]), np.array([100.0]), np.array([90.0]), 0.10
    )
    # Half of the value is gain: 5% of each dollar sold goes to tax.
    sold = 90 / (1 - 0.10 * 0.5)
    assert raised[0] == pytest.approx(90)
    assert tax[0] == pytest.approx(sold * 0.05)
    assert value[0] == pytest.approx(200 - sold)
    assert basis[0] == pytest.approx(100 * (1 - sold / 200))


def test_no_tax_without_gains():
    sim = simulate(buckets(36), tax_rate=0.08)
    assert sim["total_tax_paid"] == pytest.approx(0)


def test_tax_is_paid_when_appreciated_assets_are_sold():
    growth = [0.50] + [0.0] * 35
    untaxed = simulate(buckets(36, growth=growth))
    taxed = simulate(buckets(36, growth=growth), tax_rate=0.08)
    assert taxed["total_tax_paid"] > 0
    assert taxed["ending_balance"] == pytest.approx(
        untaxed["ending_balance"] - taxed["total_tax_paid"]
    )


def test_excise_tax_lowers_the_fund():
    untaxed = run(initial_capital=200_000, annual_payout=3_000)
    taxed = run(initial_capital=200_000, annual_payout=3_000,
                excise_tax_rate=0.30)
    for name in ("Balanced", "Growth"):
        assert taxed["portfolios"][name]["mc_tax_paid_p50"] > 0
        assert (
            taxed["portfolios"][name]["mc_ending_balance_p50"]
            < untaxed["portfolios"][name]["mc_ending_balance_p50"]
        )
    assert taxed["client_inputs"]["excise_tax_rate"] == 0.30


# ---------- private equity ----------

def test_locked_private_equity_cannot_pay_scholarships():
    alloc = allocation(reserve=0.0, low=0.0, growth=0.0, pe=50_000)
    sim = simulate(buckets(24), alloc, pe_lock_years=1)
    history = sim["history"]
    assert history["pe_payment"].iloc[:12].max() == 0
    assert (history["shortfall"].iloc[:12] > 0).all()
    assert sim["illiquidity_failure"]
    # Once unlocked, private equity pays.
    assert history["shortfall"].iloc[12:].max() < 1e-6
    assert history["pe_payment"].iloc[12] > 0


def test_private_equity_takes_its_share_of_the_fund():
    p = run()["portfolios"]["Growth"]
    assert p["amounts"][PE_LABEL] == pytest.approx(100_000 * PE_SHARE)
    assert p["weights"][PE_LABEL] == pytest.approx(PE_SHARE)


def test_private_equity_share_grows_as_public_assets_pay():
    p = run(annual_payout=6_000)["portfolios"]["Conservative"]
    assert p["mc_pe_share_max_p50"] > PE_SHARE


def test_no_private_equity():
    p = run(pe_share=0.0)["portfolios"]["Growth"]
    assert PE_LABEL not in p["amounts"]
    assert p["mc_pe_share_max_p50"] == 0


def test_private_equity_stress_shock():
    assert portfolio_stress_shock({PE_LABEL: 1.0}) == pytest.approx(-0.30)


# ---------- allocation rules ----------

def test_class_shares_follow_the_risk_profile():
    result = run()
    for name, p in result["portfolios"].items():
        assert p["available"], name
        assert sum(p["amounts"].values()) == pytest.approx(100_000)
        assert sum(p["weights"].values()) == pytest.approx(1.0)
        assert p["bond_share_of_public"] == pytest.approx(BOND_SHARE[name])
        assert p["bond_share_of_public"] >= MIN_CLASS_SHARE
        assert p["stock_share_of_public"] >= MIN_CLASS_SHARE


def test_riskier_strategies_unavailable_for_conservative_client():
    result = run(risk_tolerance="Conservative")
    portfolios = result["portfolios"]
    assert portfolios["Conservative"]["available"]
    assert not portfolios["Balanced"]["available"]
    assert not portfolios["Growth"]["available"]
    assert result["recommendation"] in (None, "Conservative")


def test_excluded_asset_is_replaced_within_its_class():
    full = run()["portfolios"]["Balanced"]
    screened = run(
        ethical_policy="Moderate",
        asset_metadata=metadata("Moderate", {"BIL", "BND", "BNDX", "VTI"}),
    )["portfolios"]["Balanced"]

    assert "VXUS" not in screened["amounts"]
    assert screened["amounts"]["VTI"] == pytest.approx(
        full["amounts"]["VTI"] + full["amounts"]["VXUS"]
    )
    assert screened["bond_share_of_public"] == pytest.approx(
        full["bond_share_of_public"]
    )


def test_excluded_fund_is_replaced_by_its_esg_version():
    returns = ASSET_RETURNS.assign(
        ESGV=ASSET_RETURNS["VTI"] * 0.99,
        VSGX=ASSET_RETURNS["VXUS"] * 0.99,
    )
    allowed = {"BIL", "BND", "BNDX", "VTI", "ESGV", "VSGX"}
    full = run(asset_returns=returns)["portfolios"]["Balanced"]
    screened = run(
        asset_returns=returns,
        ethical_policy="Moderate",
        asset_metadata={
            a: {"Moderate": a in allowed} for a in returns.columns
        },
    )["portfolios"]["Balanced"]

    # International stocks keep their share, now in the ESG fund.
    assert "VXUS" not in screened["amounts"]
    assert screened["amounts"]["VSGX"] == pytest.approx(
        full["amounts"]["VXUS"]
    )
    assert screened["amounts"]["VTI"] == pytest.approx(full["amounts"]["VTI"])
    assert screened["fund_substitutions"] == {
        "International stocks": {"excluded": "VXUS", "replaced_by": "VSGX"}
    }
    assert screened["uncovered_zones"] == []
    # The ESG fund is only a fallback: unused when the first fund is allowed.
    assert "VSGX" not in full["amounts"] and "ESGV" not in full["amounts"]


def test_zone_without_eligible_fund_is_reported():
    p = run(
        ethical_policy="Moderate",
        asset_metadata=metadata("Moderate", {"BIL", "BND", "BNDX", "VTI"}),
    )["portfolios"]["Balanced"]
    assert p["uncovered_zones"] == ["International stocks"]


def test_empty_asset_class_makes_strategies_unavailable():
    result = run(
        ethical_policy="Strict",
        asset_metadata=metadata("Strict", {"BIL", "BND"}),
    )
    assert result["recommendation"] is None
    assert result["eligible_strategies"] == []
    for p in result["portfolios"].values():
        assert not p["available"]
        assert "No eligible stocks" in p["reason"]
    assert set(result["excluded_or_unverified_assets"]) == {
        "BNDX", "VTI", "VXUS"
    }


def test_reserve_counts_in_bonds_and_bills():
    p = run(annual_payout=5_000)["portfolios"]["Growth"]
    bonds = sum(p["amounts"][a] for a in ("BIL", "BND", "BNDX"))
    assert bonds == pytest.approx(80_000 * BOND_SHARE["Growth"])
    assert p["amounts"]["BIL"] >= p["reserve_amount"]


# ---------- funding tests and recommendation ----------

def test_failing_strategies_are_not_recommended():
    # Payouts far too large for the capital: every strategy must fail.
    result = run(annual_payout=30_000, initial_capital=100_000)
    assert result["recommendation"] is None
    assert result["eligible_strategies"] == []


def test_long_horizon_can_fail_where_history_passes():
    result = run(
        annual_payout=9_000,
        horizon_years=30,
        risk_tolerance="Conservative",
    )
    p = result["portfolios"]["Conservative"]
    assert p["mc_success_rate"] < 0.90
    assert result["recommendation"] is None


def test_stress_shock_depends_on_assets():
    assert portfolio_stress_shock({"BIL": 1.0}) == pytest.approx(0.0)
    assert portfolio_stress_shock({"VTI": 1.0}) == pytest.approx(-0.40)
    portfolios = run()["portfolios"]
    assert (
        portfolios["Conservative"]["stress_shock"]
        > portfolios["Growth"]["stress_shock"]
    )


def test_results_are_reproducible():
    first = run()["portfolios"]["Balanced"]["mc_success_rate"]
    second = run()["portfolios"]["Balanced"]["mc_success_rate"]
    assert first == second


def test_recommends_strategy_matching_profile():
    result = run(initial_capital=200_000, annual_payout=3_000)
    assert result["portfolios"]["Growth"]["failed_checks"] == []
    assert result["recommendation"] == "Growth"
    assert "matches the client's risk tolerance" in (
        result["recommendation_reason"]
    )


def test_falls_back_to_next_less_risky_strategy(monkeypatch):
    original = finance.failed_funding_checks

    def growth_fails(result, min_success_rate):
        if result["bond_share_of_public"] == pytest.approx(BOND_SHARE["Growth"]):
            return ["stress success rate 80.0% below 90%"]
        return original(result, min_success_rate)

    monkeypatch.setattr(finance, "failed_funding_checks", growth_fails)
    result = run(initial_capital=200_000, annual_payout=3_000)
    assert result["recommendation"] == "Balanced"
    assert "Not retained: Growth (stress success rate" in (
        result["recommendation_reason"]
    )


def test_real_value_metrics():
    p = run(initial_capital=200_000, annual_payout=3_000)["portfolios"]["Growth"]
    assert 0 <= p["mc_real_value_preserved_rate"] <= 1
    assert p["mc_real_ending_balance_p50"] < p["mc_ending_balance_p50"]
