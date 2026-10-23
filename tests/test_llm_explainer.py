"""Offline tests for the LLM layer: the Azure client is faked."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scholarfund import llm_explainer
from scholarfund.finance import recommend_portfolio

rng = np.random.default_rng(0)
dates = pd.date_range("2016-01-31", periods=120, freq="ME")
RETURNS = pd.DataFrame({
    "BIL": rng.normal(0.003, 0.001, 120),
    "BND": rng.normal(0.004, 0.015, 120),
    "VTI": rng.normal(0.009, 0.045, 120),
    "VXUS": rng.normal(0.007, 0.050, 120),
}, index=dates)


def analysis_result():
    result = recommend_portfolio(
        RETURNS,
        risk_tolerance="Growth",
        initial_capital=200_000,
        annual_payout=3_000,
        n_simulations=100,
    )
    result["sustainable_payouts"] = None
    result["data_context"] = {
        "market_data": {"first_month": "2016-01-31", "n_months": 120},
        "macro": {"source": "test", "inflation_rate": 0.03},
        "ethics": None,
        "generated_on": "2026-10-23",
    }
    return result


class FakeClient:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_payload_is_json_and_drops_histories():
    payload = llm_explainer.build_llm_payload(analysis_result())
    text = json.dumps(payload)
    assert "balance_history" not in text
    assert payload["recommendation"] == "Growth"
    assert set(payload["strategies"]) == {"Conservative", "Balanced", "Growth"}


def test_explain_sends_rules_and_data():
    client = FakeClient("Recommendation: Growth.")
    text, payload = llm_explainer.explain_result(
        analysis_result(), language="French", client=client
    )
    assert text == "Recommendation: Growth."

    messages = client.calls[0]["messages"]
    assert messages[0]["content"] == llm_explainer.SYSTEM_PROMPT
    assert "Write the explanation in French." in messages[1]["content"]
    assert '"recommendation": "Growth"' in messages[1]["content"]


def test_unverified_numbers_flags_invented_figures():
    payload = {
        "rate": 0.0341,
        "payout": 5000,
        "strategies": {"Growth": {"stress_success_rate": 0.4283}},
    }
    text = (
        "Inflation is 3.41% and the payout is $5,000. Growth passed "
        "42.8% of stressed paths over 20 years since 2007, but it "
        "returned 9.5% a year."
    )
    assert llm_explainer.unverified_numbers(text, payload) == ["9.5%"]


def test_missing_azure_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    from scholarfund.config import MissingApiKeyError
    with pytest.raises(MissingApiKeyError, match="AZURE_OPENAI_API_KEY"):
        llm_explainer.get_client()


def test_signs_are_ignored_when_checking_numbers():
    payload = {"stress_shock": -0.1278, "maximum_drawdown": -0.2725}
    text = "A −12.78% shock and a 27.25% decline."
    assert llm_explainer.unverified_numbers(text, payload) == []


def test_sustainable_payouts_are_rounded():
    result = analysis_result()
    result["sustainable_payouts"] = {"Growth": 3994.53, "Balanced": None}
    payouts = llm_explainer.build_llm_payload(result)["sustainable_payouts"]
    assert payouts["Growth"] == 4000
    assert payouts["Balanced"] is None
    assert "nearest $50" in payouts["precision"]


def test_french_number_format_is_understood():
    payload = {"reserve": 8120.38, "weight": 0.3889, "payout": 4000}
    text = "Réserve de 8 120 $, BIL à 38,89 %, versement de 4 000 $."
    assert llm_explainer.unverified_numbers(text, payload) == []
    assert llm_explainer.normalize_number_format("5,000 et 3,41 %") == (
        "5,000 et 3.41 %"
    )
