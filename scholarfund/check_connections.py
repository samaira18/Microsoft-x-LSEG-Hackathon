"""
ScholarFund AI
Check that every external data source answers with the configured keys.

Run from the project root: python -m scholarfund.check_connections
Keys are never printed.
"""

from .config import MissingApiKeyError
from .sources import finnhub_data, fred_data, wikirate_data


def check(label, call):
    try:
        print(f"[OK]   {label}: {call()}")
    except MissingApiKeyError as error:
        print(f"[KEY]  {label}: {error}")
    except finnhub_data.FinnhubAccessError as error:
        print(f"[PLAN] {label}: {error}")
    except Exception as error:
        print(f"[FAIL] {label}: {type(error).__name__}: {error}")


def fred_inflation():
    return f"10-year inflation {fred_data.get_inflation_assumption():.2%}"


def fred_tbill():
    rate, date = fred_data.get_tbill_rate()
    return f"3-month T-bill {rate:.2%} ({date.date()})"


def finnhub_quote():
    quote = finnhub_data.get_quote("VTI")
    return f"VTI {quote['current']}"


def finnhub_profile():
    return finnhub_data.get_company_profile("AAPL").get("name")


def finnhub_news():
    return f"{len(finnhub_data.get_company_news('AAPL', days=7))} articles"


def finnhub_etf_holdings():
    return f"{len(finnhub_data.get_etf_holdings('VTI'))} holdings"


def finnhub_esg():
    return f"{len(finnhub_data.get_esg_score('AAPL'))} fields"


def wikirate_search():
    companies = wikirate_data.search_companies("Apple", max_items=5)
    return f"{len(companies)} companies found"


if __name__ == "__main__":
    print("--- FRED ---")
    check("Inflation (CPIAUCSL)", fred_inflation)
    check("T-bill rate (TB3MS)", fred_tbill)

    print("\n--- Finnhub ---")
    check("Quote", finnhub_quote)
    check("Company profile", finnhub_profile)
    check("Company news", finnhub_news)
    check("ETF holdings (premium)", finnhub_etf_holdings)
    check("ESG score (premium)", finnhub_esg)

    print("\n--- Wikirate ---")
    check("Company search", wikirate_search)
