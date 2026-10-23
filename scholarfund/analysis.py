"""
ScholarFund AI
End-to-end analysis: gathers every data source, runs the financial model
and returns one result dictionary, ready to be explained by the LLM layer.
"""

from functools import lru_cache

import pandas as pd

from .config import MissingApiKeyError
from .ethics import build_asset_metadata
from .finance import (
    INFLATION_RATE,
    RISK_ORDER,
    estimate_sustainable_payout,
    recommend_portfolio,
)
from .sources import fred_data
from .sources.market_data import get_market_data


def load_macro_assumptions(inflation_years=10):
    """
    Inflation assumption and short-term rate from FRED.

    Falls back to the model's default inflation if FRED is unavailable,
    and says so in the returned "source" field.
    """
    try:
        inflation = fred_data.get_inflation_assumption(years=inflation_years)
        latest_inflation, inflation_date = fred_data.get_latest_inflation()
        tbill_rate, tbill_date = fred_data.get_tbill_rate()
    except (MissingApiKeyError, fred_data.FredError, OSError) as error:
        return {
            "source": f"default (FRED unavailable: {error})",
            "inflation_rate": INFLATION_RATE,
            "latest_inflation": None,
            "tbill_rate": None,
        }

    return {
        "source": "FRED",
        "inflation_rate": inflation,
        "inflation_method": (
            f"Annualized CPI (CPIAUCSL) over {inflation_years} years"
        ),
        "latest_inflation": latest_inflation,
        "latest_inflation_date": str(inflation_date.date()),
        "tbill_rate": tbill_rate,
        "tbill_date": str(tbill_date.date()),
    }


# Market and macro data change at most once a day: keep them in memory so
# repeated requests (e.g. from the web app) do not download them again.
@lru_cache(maxsize=4)
def _cached_market_data(period, day):
    return get_market_data(period=period)


_MACRO_CACHE = {}


def _cached_macro(day):
    # Only successful FRED answers are cached, so a temporary outage does
    # not pin the default inflation for the rest of the day.
    if day not in _MACRO_CACHE:
        macro = load_macro_assumptions()
        if macro["source"] != "FRED":
            return macro
        _MACRO_CACHE[day] = macro
    return _MACRO_CACHE[day]


def run_analysis(
    risk_tolerance="Balanced",
    ethical_policy="Standard",
    annual_payout=5_000,
    initial_capital=100_000,
    inflation_rate=None,
    period="max",
    **model_options,
):
    """
    Run the full ScholarFund analysis for one client profile.

    inflation_rate: the client's own assumption; None uses FRED's
    10-year CPI inflation (or the model default if FRED is unavailable).
    """
    today = str(pd.Timestamp.today().date())
    prices, monthly_returns = _cached_market_data(period, today)
    macro = dict(_cached_macro(today))

    if inflation_rate is not None:
        macro["fred_inflation_rate"] = macro["inflation_rate"]
        macro["inflation_rate"] = float(inflation_rate)
        macro["source"] = "client choice (FRED value kept for reference)"

    if ethical_policy == "Standard":
        asset_metadata, ethics_reports = None, None
    else:
        asset_metadata, ethics_reports = build_asset_metadata(
            list(monthly_returns.columns)
        )

    options = {
        "ethical_policy": ethical_policy,
        "inflation_rate": macro["inflation_rate"],
        "initial_capital": initial_capital,
        "asset_metadata": asset_metadata,
        **model_options,
    }
    result = recommend_portfolio(
        monthly_returns,
        risk_tolerance=risk_tolerance,
        annual_payout=annual_payout,
        **options,
    )

    # If nothing passes, tell the client which payout would be sustainable.
    result["sustainable_payouts"] = None
    if result["recommendation"] is None:
        result["sustainable_payouts"] = {
            name: estimate_sustainable_payout(
                monthly_returns, name, annual_payout, **options
            )
            for name in RISK_ORDER[:RISK_ORDER.index(risk_tolerance) + 1]
            if result["portfolios"][name]["available"]
            and not result["portfolios"][name].get("same_allocation_as")
        }

    result["data_context"] = {
        "market_data": {
            "source": "Yahoo Finance (adjusted daily closes, month-end)",
            "assets": list(monthly_returns.columns),
            "first_month": str(monthly_returns.index.min().date()),
            "last_month": str(monthly_returns.index.max().date()),
            "n_months": len(monthly_returns),
            "proxies": monthly_returns.attrs.get("proxies", {}),
        },
        "macro": macro,
        "ethics": ethics_reports,
        "generated_on": str(pd.Timestamp.today().date()),
    }
    return result


def print_summary(result):
    inputs = result["client_inputs"]
    context = result["data_context"]
    macro = context["macro"]

    print("\n=== SCHOLARFUND AI — ANALYSIS ===")
    print(f"Profile: {inputs['risk_tolerance']} / {inputs['ethical_policy']}")
    print(f"Recommended strategy: {result['recommendation']} "
          f"({result['recommendation_status']})")
    print(f"Why: {result['recommendation_reason']}")
    if result["sustainable_payouts"]:
        print("Highest payout passing every test, per strategy:")
        for name, payout in result["sustainable_payouts"].items():
            print(f"  {name}: ${payout:,.0f} per year")

    print(f"\nInflation assumption: {inputs['inflation_rate']:.2%} "
          f"[{macro['source']}]")
    if macro["tbill_rate"] is not None:
        print(f"Latest CPI inflation: {macro['latest_inflation']:.2%}; "
              f"3-month T-bill: {macro['tbill_rate']:.2%}")
    print(f"Reserve: ${inputs['reserve_amount']:,.0f} in "
          f"{inputs['reserve_asset'] or 'cash at 0%'}; invested: "
          f"${inputs['investable_capital']:,.0f}")
    market = context["market_data"]
    print(f"Market data: {market['first_month']} to {market['last_month']} "
          f"({market['n_months']} months)")
    for asset, proxy in market["proxies"].items():
        print(f"  {asset}: {proxy['proxy']} returns used until "
              f"{proxy['until']}")

    if context["ethics"]:
        print("\nEthical screening:")
        for ticker, report in context["ethics"].items():
            policy = inputs["ethical_policy"]
            status = "eligible" if report["eligible"][policy] else "EXCLUDED"
            print(f"  {ticker}: {status} — {report['reasons'][policy]}")

    for name, p in result["portfolios"].items():
        print(f"\n--- {name} ---")
        if not p["available"]:
            print(f"Unavailable: {p['reason']}")
            continue
        weights = ", ".join(f"{a} {w:.0%}" for a, w in p["weights"].items())
        print(f"Weights: {weights}")
        print(f"Return {p['annualized_return']:.2%}, volatility "
              f"{p['annualized_volatility']:.2%}, max drawdown "
              f"{p['maximum_drawdown']:.2%}")
        print(f"Success rate: {p['mc_success_rate']:.1%} normal, "
              f"{p['stress_success_rate']:.1%} stress "
              f"({p['stress_shock']:.1%} shock)")
        if p.get("same_allocation_as"):
            print(f"Same allocation as {p['same_allocation_as']}.")
        for check in p["failed_checks"]:
            print(f"Fails: {check}")

    print("\nDisclaimer:", result["disclaimer"])


if __name__ == "__main__":
    for policy in ("Standard", "Moderate", "Strict"):
        print_summary(run_analysis(
            risk_tolerance="Growth",
            ethical_policy=policy,
            annual_payout=5_000,
        ))
