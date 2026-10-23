"""
ScholarFund AI
Ethical screening of the ETFs, built from free data only (proof of concept).

For each ETF:
- equity funds: the top holdings published by Yahoo Finance (about 10)
  are screened for excluded activities (sector/industry from Yahoo) and
  for a public human rights commitment (Wikirate, World Benchmarking
  Alliance). A climate indicator (SBTi 1.5°C commitment) is reported
  for information only;
- bond and cash funds: no company holdings are available for free, so
  they are judged on their share of US government debt.

Limits, stated in every report: only the top holdings are screened (a
fraction of the fund), and a missing Wikirate answer never counts as a
pass. The output feeds finance.recommend_portfolio(asset_metadata=...).
"""

import json
import re
from pathlib import Path

import pandas as pd
import yfinance as yf

from .sources import wikirate_data

# Moderate: exclude funds whose top holdings include these activities.
EXCLUDED_SECTORS = {"Energy"}
EXCLUDED_INDUSTRY_KEYWORDS = ("Tobacco", "Aerospace & Defense")

# Strict: top holdings must also show a verified human rights commitment.
HUMAN_RIGHTS_METRIC = (
    "World Benchmarking Alliance", "Commitment to Respect Human Rights"
)
CLIMATE_METRIC = (
    "Science Based Targets Initiative (SBTi)",
    "Business Ambition for 1.5°C status",
)
MIN_VERIFIED_SHARE = 0.80

# A fund is treated as a bond/cash fund below this share of stocks.
MAX_STOCK_SHARE_FOR_BOND_FUND = 0.10
# Strict: bond/cash funds must hold at least this share of US government debt.
MIN_US_GOVERNMENT_SHARE = 0.90

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

NAME_STOPWORDS = {
    "inc", "corp", "corporation", "plc", "ltd", "limited", "ag", "nv",
    "co", "sa", "se", "holding", "holdings", "company", "the", "class",
    "registered", "shares", "ordinary", "new",
}


def normalize_name(name):
    """Lower-case company name without punctuation or legal suffixes."""
    name = re.sub(r"\(.*?\)", " ", name.lower())
    words = re.findall(r"[a-z0-9]+", name)
    return " ".join(word for word in words if word not in NAME_STOPWORDS)


def resolve_wikirate_company(name):
    """
    Find the Wikirate company card matching a Yahoo company name.

    Tries the exact card first, then a search on the first word, keeping
    only a candidate whose normalized name is identical. Returns None
    rather than guessing.
    """
    try:
        card = wikirate_data.get_company(name)
        if card.get("type") == "Company":
            return card["name"]
    except wikirate_data.WikirateError:
        pass

    first_word = re.findall(r"[A-Za-z0-9]+", name)[0]
    candidates = wikirate_data.search_companies(first_word, max_items=20)
    target = normalize_name(name)

    for candidate in candidates.get("name", []):
        if normalize_name(candidate) == target:
            return candidate
    return None


def latest_answer(metric, company):
    """Latest Wikirate answer as a dict, or None if there is none."""
    if company is None:
        return None
    answers = wikirate_data.get_metric_company_answers(*metric, company)
    if answers.empty:
        return None

    latest = answers.iloc[-1]
    return {
        "value": latest["value"],
        "year": int(latest["year"]),
        "url": latest.get("answer_url"),
    }


def excluded_activity(sector, industry):
    """Name of the excluded activity, or None."""
    if sector in EXCLUDED_SECTORS:
        return f"{sector} sector ({industry})"
    for keyword in EXCLUDED_INDUSTRY_KEYWORDS:
        if industry and keyword in industry:
            return industry
    return None


def screen_holding(symbol, weight):
    info = yf.Ticker(symbol).info
    name = info.get("longName") or info.get("shortName") or symbol
    sector = info.get("sector")
    industry = info.get("industry")
    wikirate_name = resolve_wikirate_company(name)

    return {
        "symbol": symbol,
        "name": name,
        "weight": float(weight),
        "sector": sector,
        "industry": industry,
        "excluded_activity": excluded_activity(sector, industry),
        "wikirate_company": wikirate_name,
        "human_rights_commitment": latest_answer(
            HUMAN_RIGHTS_METRIC, wikirate_name
        ),
        "climate_commitment": latest_answer(CLIMATE_METRIC, wikirate_name),
    }


def screen_etf(ticker):
    """Screen one ETF and return its eligibility per policy, with reasons."""
    funds = yf.Ticker(ticker).funds_data
    asset_classes = funds.asset_classes or {}
    stock_share = float(asset_classes.get("stockPosition", 0.0))

    report = {
        "asset": ticker,
        "stock_share": stock_share,
        "holdings": [],
        "eligible": {"Standard": True},
        "reasons": {},
    }

    # Bond and cash funds: judged on their share of US government debt.
    if stock_share < MAX_STOCK_SHARE_FOR_BOND_FUND:
        ratings = funds.bond_ratings or {}
        government = float(ratings.get("us_government", 0.0))
        report["fund_type"] = "bond_or_cash"
        report["us_government_share"] = government

        report["eligible"]["Moderate"] = True
        report["reasons"]["Moderate"] = (
            "Bond/cash fund: company-level holdings are not available for "
            "free, so it is not screened at company level."
        )

        report["eligible"]["Strict"] = government >= MIN_US_GOVERNMENT_SHARE
        report["reasons"]["Strict"] = (
            f"{government:.0%} US government debt "
            f"(minimum {MIN_US_GOVERNMENT_SHARE:.0%}); the rest cannot be "
            "screened with free data."
        )
        return report

    # Equity funds: screen the published top holdings.
    report["fund_type"] = "equity"
    top = funds.top_holdings
    holdings = [
        screen_holding(symbol, row["Holding Percent"])
        for symbol, row in top.iterrows()
    ]
    report["holdings"] = holdings

    screened_weight = sum(h["weight"] for h in holdings)
    report["screened_fund_weight"] = screened_weight

    if not holdings:
        for policy in ("Moderate", "Strict"):
            report["eligible"][policy] = False
            report["reasons"][policy] = "No holdings data available."
        return report

    excluded = [h for h in holdings if h["excluded_activity"]]
    report["eligible"]["Moderate"] = not excluded
    report["reasons"]["Moderate"] = (
        "Excluded activities among top holdings: " + "; ".join(
            f"{h['name']} ({h['excluded_activity']})" for h in excluded
        )
        if excluded else
        f"No excluded activity among the top holdings "
        f"({screened_weight:.0%} of the fund screened)."
    )

    negative = [
        h for h in holdings
        if h["human_rights_commitment"]
        and h["human_rights_commitment"]["value"] != "Yes"
    ]
    verified_weight = sum(
        h["weight"] for h in holdings
        if h["human_rights_commitment"]
        and h["human_rights_commitment"]["value"] == "Yes"
    )
    verified_share = verified_weight / screened_weight
    report["human_rights_verified_share"] = verified_share

    strict_ok = (
        report["eligible"]["Moderate"]
        and not negative
        and verified_share >= MIN_VERIFIED_SHARE
    )
    report["eligible"]["Strict"] = strict_ok

    reasons = []
    if not report["eligible"]["Moderate"]:
        reasons.append("fails the Moderate screen")
    if negative:
        reasons.append("no human rights commitment: " + ", ".join(
            h["name"] for h in negative
        ))
    reasons.append(
        f"{verified_share:.0%} of screened weight has a verified human "
        f"rights commitment (minimum {MIN_VERIFIED_SHARE:.0%})"
    )
    report["reasons"]["Strict"] = "; ".join(reasons) + "."
    return report


def build_asset_metadata(tickers, use_cache=True):
    """
    Screen every ETF and return (asset_metadata, reports).

    asset_metadata has the shape expected by finance.recommend_portfolio:
    {ticker: {"Standard": True, "Moderate": bool, "Strict": bool}}.
    Results are cached for the day in .cache/ to avoid repeated API calls.
    """
    cache_file = CACHE_DIR / f"ethics_{pd.Timestamp.today().date()}.json"
    cached = {}
    if use_cache and cache_file.exists():
        cached = json.loads(cache_file.read_text())

    reports = {}
    for ticker in tickers:
        reports[ticker] = cached.get(ticker) or screen_etf(ticker)

    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(reports, indent=1, default=str))

    metadata = {
        ticker: report["eligible"] for ticker, report in reports.items()
    }
    return metadata, reports


if __name__ == "__main__":
    metadata, reports = build_asset_metadata(["BIL", "BND", "VTI", "VXUS"])

    for ticker, report in reports.items():
        print(f"\n=== {ticker} ({report['fund_type']}) ===")
        for policy in ("Moderate", "Strict"):
            status = "eligible" if report["eligible"][policy] else "EXCLUDED"
            print(f"{policy}: {status} — {report['reasons'][policy]}")

        for h in report["holdings"]:
            rights = h["human_rights_commitment"]
            climate = h["climate_commitment"]
            print(
                f"  {h['weight']:.1%} {h['name']} | {h['sector']} | "
                f"Wikirate: {h['wikirate_company'] or 'not found'} | "
                f"HR: {rights['value'] if rights else 'n/a'} | "
                f"SBTi 1.5°C: {climate['value'] if climate else 'n/a'}"
            )
