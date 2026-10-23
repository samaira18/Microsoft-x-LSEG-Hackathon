"""
ScholarFund AI
Ethics data loader using Wikirate (open company sustainability data).

Wikirate covers companies, not funds: screening an ETF requires its
holdings first. Wikirate answers are community-researched and may be
missing or unverified, so a missing answer must never be read as "passes".
"""

import re

import pandas as pd
import requests

from ..config import get_api_key

BASE_URL = "https://wikirate.org"
TIMEOUT_SECONDS = 60
PAGE_SIZE = 100


class WikirateError(RuntimeError):
    pass


def card_key(name):
    """Turn a card name into Wikirate's URL key (same rule as wikirate4py)."""
    key = re.sub(
        r"[^a-zA-Z0-9_+~]+",
        lambda match: "+" if match.group(0) == "+" else " ",
        name,
    )
    return re.sub(r"\s+", "_", key.strip())


def _get(path, **params):
    response = requests.get(
        f"{BASE_URL}/{path}",
        params=params,
        headers={"X-API-Key": get_api_key("WIKIRATE_API_KEY")},
        timeout=TIMEOUT_SECONDS,
    )

    if "application/json" not in response.headers.get("Content-Type", ""):
        raise WikirateError(
            f"Wikirate {path} did not return JSON "
            f"(HTTP {response.status_code}). The request may have been "
            "blocked; check WIKIRATE_API_KEY."
        )
    if response.status_code != 200:
        raise WikirateError(
            f"Wikirate {path} failed with HTTP {response.status_code}."
        )

    return response.json()


def _get_items(path, max_items=None, **params):
    """Follow limit/offset pagination and return all items."""
    items = []
    offset = 0

    while True:
        page = _get(path, limit=PAGE_SIZE, offset=offset, **params)
        batch = page.get("items", [])
        items.extend(batch)
        offset += len(batch)

        if len(batch) < PAGE_SIZE:
            break
        if max_items is not None and len(items) >= max_items:
            break

    return items[:max_items] if max_items is not None else items


def search_companies(name, max_items=20):
    """Companies whose name matches `name`."""
    items = _get_items(
        "Companies.json", max_items=max_items, **{"filter[name]": name}
    )
    return pd.DataFrame(items)


def get_company(name):
    """Full company card, including identifiers such as ISIN or LEI."""
    return _get(f"{card_key(name)}.json")


def get_answers(metric_designer, metric_name, year=None, max_items=None):
    """
    Answers to one metric across companies, optionally for one year.

    Returns a DataFrame with one row per (company, year) answer. To get
    one company's answers, use get_metric_company_answers instead: the
    company filter of this endpoint is ignored by Wikirate.
    """
    params = {}
    if year is not None:
        params["filter[year]"] = str(year)

    items = _get_items(
        f"{card_key(metric_designer)}+{card_key(metric_name)}+Answers.json",
        max_items=max_items,
        **params,
    )
    return pd.DataFrame(items)


def get_metric_company_answers(metric_designer, metric_name, company):
    """
    One company's answers to one metric, one row per year (latest last).

    Returns an empty DataFrame when Wikirate has no answer.
    """
    path = (
        f"{card_key(metric_designer)}+{card_key(metric_name)}"
        f"+{card_key(company)}.json"
    )
    try:
        items = _get(path).get("items", [])
    except WikirateError:
        return pd.DataFrame()

    answers = pd.DataFrame(items)
    if not answers.empty:
        answers = answers.sort_values("year").reset_index(drop=True)
    return answers


def get_company_answers(company, max_items=None, **filters):
    """All answers about one company, across metrics."""
    params = {f"filter[{key}]": value for key, value in filters.items()}
    items = _get_items(
        f"{card_key(company)}+Answers.json", max_items=max_items, **params
    )
    return pd.DataFrame(items)


if __name__ == "__main__":
    companies = search_companies("Apple", max_items=5)
    print("Company search 'Apple':")
    print(companies.get("name", companies).to_string())

    answers = get_answers(
        "Business & Human Rights Resource Centre",
        "Modern Slavery Statement",
        max_items=5,
    )
    print("\nSample answers — Modern Slavery Statement:")
    print(answers.head().to_string())
