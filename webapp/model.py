"""
model.py - OWNER: Person 2 (Model & Data)
Bridge between the Streamlit app and the ScholarFund engine
(analysis.py / finance.py): turns the app's settings into a scenario,
runs the engine on real data, and returns what the app and the AI need.
No Streamlit, no AI calls in here.
Educational hackathon project. Not financial advice.
"""
import time

import pandas as pd

from scholarfund.analysis import _cached_macro, run_analysis
from scholarfund.finance import (
    BOND_SHARE, EXCISE_TAX_TIERS, PE_LABEL, RISK_ORDER, monthly_payment_due,
)
from scholarfund.llm_explainer import build_llm_payload

# ---------------------------------------------------------------------
# HARVARD FACTS (FY2026 report, published Oct 2026) - VERIFY before presenting
# ---------------------------------------------------------------------
HARVARD = {
    "endowment_bn": 68.0, "endowment_prev_bn": 56.9,
    "ret_fy24": 9.6, "ret_fy25": 11.9, "ret_fy26": 27.1, "target": 8.0,
    "distribution_bn": 2.6,      # secondary source - double-check
    "aid_m": 775,
    "tax_old": 1.4, "tax_new": 8.0,
    "pe_share_today": 40,        # "over 40%" in private equity - verify
}

# ---------------------------------------------------------------------
# ASSETS, PROFILES AND CONTROLS
# ---------------------------------------------------------------------
ASSET_NAMES = {
    "BIL": "Cash (Treasury bills)",
    "BND": "US bonds",
    "BNDX": "International bonds",
    "VTI": "US equities",
    "VXUS": "International equities",
    "ESGV": "US equities (ESG)",
    "VSGX": "International equities (ESG)",
    PE_LABEL: "Private equity (illiquid)",
    "Cash": "Cash (uninvested)",
}
TICKERS = ["BIL", "BND", "BNDX", "VTI", "VXUS", "ESGV", "VSGX"]
ASSETS = [ASSET_NAMES[t] for t in TICKERS]
# Share of public markets in bonds and bills, per risk profile.
PROFILES = {name: BOND_SHARE[name] for name in RISK_ORDER}
ETHICS = ["Standard", "Moderate", "Strict"]
ETHICS_LABELS = {
    "Standard": "No screen",
    "Moderate": "Excludes fossil fuels, tobacco, weapons",
    "Strict": "Moderate + verified human rights commitments",
}
# Private equity share options: none, the model's target, Harvard today.
PE_CHOICES = [0, 20, 40]
TAX_TIERS_PCT = {name: rate * 100 for name, rate in EXCISE_TAX_TIERS.items()}


def _fred_inflation():
    """FRED 10-year CPI inflation in %, or 3.0 if FRED is unavailable."""
    macro = _cached_macro(str(pd.Timestamp.today().date()))
    return round(macro["inflation_rate"] * 100, 1)


# Shown next to the inflation slider as a reference.
FRED_INFLATION = _fred_inflation()

# Starting values for every control in the app
DEFAULTS = {"risk": "Balanced", "ethics": "Moderate", "pe": 20,
            "tax_on": True, "tax": 2.0,
            "payout": 4.0, "gift": 100_000, "years": 10,
            "infl": 3.0}


# ---------------------------------------------------------------------
# SCENARIO
# ---------------------------------------------------------------------
def _engine_inputs(s, tax_pct=None, pe_pct=None):
    if tax_pct is None:
        tax_pct = s["tax"] if s["tax_on"] else 0.0
    if pe_pct is None:
        pe_pct = s["pe"]
    return {
        "risk_tolerance": s["risk"],
        "ethical_policy": s["ethics"],
        "annual_payout": s["gift"] * s["payout"] / 100,
        "initial_capital": s["gift"],
        "inflation_rate": s["infl"] / 100,
        "horizon_years": int(s["years"]),
        "excise_tax_rate": tax_pct / 100,
        "pe_share": pe_pct / 100,
    }


def _shown_strategy(result, risk):
    """Recommended strategy, else the client's own profile if available."""
    if result["recommendation"]:
        return result["recommendation"]
    available = [
        name for name in RISK_ORDER[:RISK_ORDER.index(risk) + 1][::-1]
        if result["portfolios"][name]["available"]
    ]
    return available[0] if available else None


def _compare(s, shown, **override):
    """Same scenario with one setting changed, for side-by-side tabs."""
    result = run_analysis(**_engine_inputs(s, **override))
    return {
        "result": result,
        "portfolio": result["portfolios"][shown] if shown else None,
    }


def run_scenario(s):
    """Takes the settings dict (keys of DEFAULTS), returns everything the app and the AI need."""
    inputs = _engine_inputs(s)
    result = run_analysis(**inputs)
    shown = _shown_strategy(result, s["risk"])
    portfolio = result["portfolios"][shown] if shown else None

    # Endowment tax: compare with the tax switched off, or, if it is
    # already off, with Harvard's 8% tier.
    tax_now = inputs["excise_tax_rate"] * 100
    tax_other = 0.0 if tax_now else HARVARD["tax_new"]
    # Private equity: compare the target 20% with Harvard's 40% today.
    pe_other = 20 if s["pe"] == 40 else 40

    # Dollars per asset class, reserve included (it is held in BIL).
    alloc = {}
    if portfolio:
        for asset, amount in portfolio["amounts"].items():
            name = ASSET_NAMES.get(asset, asset)
            alloc[name] = alloc.get(name, 0) + round(amount)

    # Scholarships promised over the horizon if every payment is made.
    total_promised = sum(
        monthly_payment_due(m, inputs["annual_payout"], inputs["inflation_rate"])
        for m in range(int(s["years"]) * 12)
    )

    return {
        "result": result,
        "payload": build_llm_payload(result),
        "shown_strategy": shown,
        "recommended": result["recommendation"] is not None,
        "portfolio": portfolio,
        "tax_pct": tax_now,
        "tax_compare_pct": tax_other,
        "tax_compare": _compare(s, shown, tax_pct=tax_other),
        "pe_compare_pct": pe_other,
        "pe_compare": _compare(s, shown, pe_pct=pe_other),
        "annual_payout": inputs["annual_payout"],
        "reserve": result["client_inputs"]["reserve_amount"],
        "alloc": alloc,
        "total_promised": total_promised,
    }


# ---------------------------------------------------------------------
# LIVE DATA (optional - app still works offline)
# ---------------------------------------------------------------------
_snap = {"t": 0.0, "data": None}


def market_snapshot():
    """1-year ETF returns from Yahoo Finance, cached 1 hour. Returns None if offline."""
    if time.time() - _snap["t"] < 3600:
        return _snap["data"]
    try:
        import yfinance as yf
        px = yf.download(TICKERS, period="1y", progress=False, auto_adjust=True)["Close"]
        data = {t: round(float((px[t].iloc[-1] / px[t].iloc[0] - 1) * 100), 1) for t in TICKERS}
        _snap.update(t=time.time(), data=data)
    except Exception:  # noqa
        _snap.update(t=time.time() - 3300, data=None)      # retry in 5 minutes
    return _snap["data"]
