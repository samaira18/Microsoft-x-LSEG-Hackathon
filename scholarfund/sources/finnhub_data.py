"""
ScholarFund AI
Market and company data loader using Finnhub.

Some endpoints (ETF holdings, ESG scores) are premium. When the API key
does not give access to one, FinnhubAccessError is raised so the caller
can fall back instead of inventing data.
"""

import pandas as pd
import requests

from ..config import get_api_key

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT_SECONDS = 30


class FinnhubError(RuntimeError):
    pass


class FinnhubAccessError(FinnhubError):
    """The endpoint is not included in the current Finnhub plan."""


def _get(path, **params):
    response = requests.get(
        f"{BASE_URL}{path}",
        params=params,
        headers={"X-Finnhub-Token": get_api_key("FINNHUB_API_KEY")},
        timeout=TIMEOUT_SECONDS,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None

    if response.status_code in (401, 403):
        raise FinnhubAccessError(
            f"No access to Finnhub {path}: {error or response.status_code}"
        )
    if response.status_code == 429:
        raise FinnhubError("Finnhub rate limit reached; try again later.")
    if response.status_code != 200 or error:
        raise FinnhubError(
            f"Finnhub {path} failed: {error or response.status_code}"
        )

    return payload


def get_quote(symbol):
    """Latest quote: current price, change, high, low, open, previous close."""
    data = _get("/quote", symbol=symbol)
    return {
        "symbol": symbol,
        "current": data.get("c"),
        "change": data.get("d"),
        "percent_change": data.get("dp"),
        "high": data.get("h"),
        "low": data.get("l"),
        "open": data.get("o"),
        "previous_close": data.get("pc"),
        "timestamp": pd.to_datetime(data.get("t"), unit="s"),
    }


def get_company_profile(symbol):
    """Company profile: name, country, industry, ISIN-like identifiers."""
    return _get("/stock/profile2", symbol=symbol)


def get_company_news(symbol, days=30):
    """
    Company news over the last `days` days, as a DataFrame.

    On the free plan, Finnhub returns at most about one week of recent
    articles, whatever the requested period.
    """
    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=days)
    items = _get(
        "/company-news",
        symbol=symbol,
        **{"from": str(start.date()), "to": str(end.date())},
    )

    news = pd.DataFrame(items)
    if not news.empty:
        news["datetime"] = pd.to_datetime(news["datetime"], unit="s")
        news = news[["datetime", "headline", "source", "url", "summary"]]
    return news


def get_etf_profile(symbol):
    """ETF profile: issuer, expense ratio, AUM, benchmark (premium)."""
    return _get("/etf/profile", symbol=symbol).get("profile", {})


def get_etf_holdings(symbol):
    """ETF holdings with their weight in percent (premium)."""
    data = _get("/etf/holdings", symbol=symbol)
    return pd.DataFrame(data.get("holdings", []))


def get_esg_score(symbol):
    """Company ESG score and its components (premium)."""
    return _get("/stock/esg", symbol=symbol)


if __name__ == "__main__":
    for symbol in ["VTI", "BND"]:
        quote = get_quote(symbol)
        print(f"{symbol}: {quote['current']} ({quote['percent_change']}%)")

    profile = get_company_profile("AAPL")
    print(f"AAPL profile: {profile.get('name')}, {profile.get('country')}, "
          f"{profile.get('finnhubIndustry')}")

    news = get_company_news("AAPL", days=7)
    print(f"AAPL news over 7 days: {len(news)} articles")

    for label, call in [
        ("ETF profile VTI", lambda: get_etf_profile("VTI")),
        ("ETF holdings VTI", lambda: get_etf_holdings("VTI")),
        ("ESG score AAPL", lambda: get_esg_score("AAPL")),
    ]:
        try:
            result = call()
            print(f"{label}: available ({len(result)} fields/rows)")
        except FinnhubAccessError as error:
            print(f"{label}: not in this plan ({error})")
