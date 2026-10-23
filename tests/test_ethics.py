"""Offline tests for the ethical screening: Yahoo and Wikirate are faked."""

import pandas as pd
import pytest

from scholarfund import ethics


class FakeFunds:
    def __init__(self, stock_share, holdings=None, us_government=0.0):
        self.asset_classes = {"stockPosition": stock_share}
        self.bond_ratings = {"us_government": us_government}
        self.top_holdings = pd.DataFrame(
            {"Holding Percent": [w for _, w in holdings or []]},
            index=[s for s, _ in holdings or []],
        )


class FakeTicker:
    def __init__(self, symbol):
        self.funds_data = FUNDS.get(symbol)
        self.info = COMPANIES.get(symbol, {})


FUNDS = {}
COMPANIES = {
    "AAA": {"longName": "Alpha Inc.", "sector": "Technology",
            "industry": "Software"},
    "BBB": {"longName": "Beta Oil plc", "sector": "Energy",
            "industry": "Oil & Gas Integrated"},
    "CCC": {"longName": "Gamma Corp", "sector": "Industrials",
            "industry": "Aerospace & Defense"},
    "DDD": {"longName": "Delta Ltd", "sector": "Healthcare",
            "industry": "Drug Manufacturers"},
}
HUMAN_RIGHTS = {"Alpha Inc.": "Yes", "Delta Ltd": "No"}


@pytest.fixture(autouse=True)
def fake_sources(monkeypatch):
    monkeypatch.setattr(ethics.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(ethics, "resolve_wikirate_company", lambda name: name)

    def latest_answer(metric, company):
        if metric == ethics.HUMAN_RIGHTS_METRIC and company in HUMAN_RIGHTS:
            return {"value": HUMAN_RIGHTS[company], "year": 2025, "url": None}
        return None

    monkeypatch.setattr(ethics, "latest_answer", latest_answer)
    FUNDS.clear()


def test_normalize_name_ignores_suffixes_and_punctuation():
    assert (
        ethics.normalize_name("Taiwan Semiconductor Manufacturing Company "
                              "Limited")
        == ethics.normalize_name("Taiwan Semiconductor Manufacturing "
                                 "Company (TSMC)")
    )
    assert ethics.normalize_name("Roche Holding AG") == "roche"


def test_excluded_activities():
    assert ethics.excluded_activity("Energy", "Oil & Gas") is not None
    assert ethics.excluded_activity("Industrials", "Aerospace & Defense")
    assert ethics.excluded_activity("Technology", "Software") is None


def test_government_bond_fund_passes_strict():
    FUNDS["GOV"] = FakeFunds(0.0, us_government=0.99)
    report = ethics.screen_etf("GOV")
    assert report["eligible"] == {
        "Standard": True, "Moderate": True, "Strict": True
    }


def test_mixed_bond_fund_fails_strict_only():
    FUNDS["AGG"] = FakeFunds(0.0, us_government=0.50)
    report = ethics.screen_etf("AGG")
    assert report["eligible"]["Moderate"]
    assert not report["eligible"]["Strict"]


def test_excluded_activity_fails_moderate_and_strict():
    FUNDS["EQ"] = FakeFunds(1.0, [("AAA", 0.05), ("BBB", 0.01)])
    report = ethics.screen_etf("EQ")
    assert not report["eligible"]["Moderate"]
    assert not report["eligible"]["Strict"]
    assert "Beta Oil plc" in report["reasons"]["Moderate"]


def test_defense_industry_is_excluded():
    FUNDS["EQ"] = FakeFunds(1.0, [("AAA", 0.05), ("CCC", 0.01)])
    assert not ethics.screen_etf("EQ")["eligible"]["Moderate"]


def test_verified_commitments_pass_strict():
    FUNDS["EQ"] = FakeFunds(1.0, [("AAA", 0.05)])
    report = ethics.screen_etf("EQ")
    assert report["eligible"]["Strict"]
    assert report["human_rights_verified_share"] == pytest.approx(1.0)


def test_negative_answer_fails_strict():
    FUNDS["EQ"] = FakeFunds(1.0, [("AAA", 0.09), ("DDD", 0.01)])
    report = ethics.screen_etf("EQ")
    assert report["eligible"]["Moderate"]
    assert not report["eligible"]["Strict"]


def test_missing_answers_do_not_count_as_verified():
    # Gamma has no answer and is excluded anyway; use an unknown company.
    COMPANIES["EEE"] = {"longName": "Unknown SA", "sector": "Technology",
                        "industry": "Software"}
    FUNDS["EQ"] = FakeFunds(1.0, [("AAA", 0.05), ("EEE", 0.05)])
    report = ethics.screen_etf("EQ")
    assert report["human_rights_verified_share"] == pytest.approx(0.5)
    assert not report["eligible"]["Strict"]


def test_no_holdings_data_fails_both_policies():
    FUNDS["EQ"] = FakeFunds(1.0, [])
    report = ethics.screen_etf("EQ")
    assert not report["eligible"]["Moderate"]
    assert not report["eligible"]["Strict"]
