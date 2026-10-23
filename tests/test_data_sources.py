"""Offline tests for the API connectors: HTTP calls are replaced by fakes."""

import pytest

from scholarfund import config
from scholarfund.sources import finnhub_data, fred_data, wikirate_data


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content_type=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = {
            "Content-Type": content_type or "application/json"
        }

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def fake_keys(monkeypatch):
    for name in ["FRED_API_KEY", "FINNHUB_API_KEY", "WIKIRATE_API_KEY"]:
        monkeypatch.setenv(name, "test-key")


def fake_get(monkeypatch, module, *responses):
    calls = []
    queue = list(responses)

    def get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return queue.pop(0)

    monkeypatch.setattr(module.requests, "get", get)
    return calls


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY")
    with pytest.raises(config.MissingApiKeyError, match="FRED_API_KEY"):
        fred_data.get_series("CPIAUCSL")


def test_fred_series_drops_missing_values(monkeypatch):
    payload = {"observations": [
        {"date": "2026-01-01", "value": "320.0"},
        {"date": "2026-02-01", "value": "."},
        {"date": "2026-03-01", "value": "321.5"},
    ]}
    calls = fake_get(monkeypatch, fred_data, FakeResponse(payload=payload))

    series = fred_data.get_series("CPIAUCSL")
    assert list(series) == [320.0, 321.5]
    assert calls[0]["params"]["api_key"] == "test-key"


def test_fred_error_message_is_reported(monkeypatch):
    payload = {"error_message": "Bad Request. The series does not exist."}
    fake_get(monkeypatch, fred_data, FakeResponse(400, payload))
    with pytest.raises(fred_data.FredError, match="does not exist"):
        fred_data.get_series("NOPE")


def test_finnhub_premium_endpoint_raises_access_error(monkeypatch):
    payload = {"error": "You don't have access to this resource."}
    fake_get(monkeypatch, finnhub_data, FakeResponse(403, payload))
    with pytest.raises(finnhub_data.FinnhubAccessError):
        finnhub_data.get_etf_holdings("VTI")


def test_finnhub_key_is_sent_in_header(monkeypatch):
    payload = {"c": 300.0, "d": 1.0, "dp": 0.33, "t": 1_760_000_000}
    calls = fake_get(monkeypatch, finnhub_data, FakeResponse(payload=payload))

    quote = finnhub_data.get_quote("VTI")
    assert quote["current"] == 300.0
    assert calls[0]["headers"]["X-Finnhub-Token"] == "test-key"
    assert "token" not in calls[0]["params"]


def test_wikirate_card_key():
    assert wikirate_data.card_key("Apple Inc.") == "Apple_Inc"
    assert (
        wikirate_data.card_key("Core+Company Report Available")
        == "Core+Company_Report_Available"
    )


def test_wikirate_blocked_html_raises(monkeypatch):
    fake_get(
        monkeypatch, wikirate_data,
        FakeResponse(403, content_type="text/html; charset=UTF-8"),
    )
    with pytest.raises(wikirate_data.WikirateError, match="did not return"):
        wikirate_data.search_companies("Apple")


def test_wikirate_company_answers_sorted_and_missing(monkeypatch):
    payload = {"items": [
        {"year": 2025, "value": "Yes"},
        {"year": 2023, "value": "No"},
    ]}
    calls = fake_get(
        monkeypatch, wikirate_data,
        FakeResponse(payload=payload),
        FakeResponse(404, content_type="text/html"),
    )

    answers = wikirate_data.get_metric_company_answers(
        "World Benchmarking Alliance",
        "Commitment to Respect Human Rights",
        "Apple Inc.",
    )
    assert list(answers["year"]) == [2023, 2025]
    assert calls[0]["url"].endswith(
        "World_Benchmarking_Alliance+Commitment_to_Respect_Human_Rights"
        "+Apple_Inc.json"
    )

    missing = wikirate_data.get_metric_company_answers("A", "B", "Nobody")
    assert missing.empty


def test_wikirate_follows_pagination(monkeypatch):
    first = {"items": [{"name": f"C{i}"} for i in range(100)]}
    second = {"items": [{"name": "C100"}]}
    calls = fake_get(
        monkeypatch, wikirate_data,
        FakeResponse(payload=first), FakeResponse(payload=second),
    )

    companies = wikirate_data.search_companies("C", max_items=None)
    assert len(companies) == 101
    assert [c["params"]["offset"] for c in calls] == [0, 100]
    assert calls[0]["headers"]["X-API-Key"] == "test-key"
