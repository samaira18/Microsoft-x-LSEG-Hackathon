"""
ScholarFund AI
LLM layer: explains the numerical results with Azure OpenAI.

The model receives a compact JSON payload built from analysis.run_analysis
and must explain it without adding facts or figures. A simple check then
lists any number in the explanation that cannot be found in the payload.
"""

import json
import os
import re
from pathlib import Path

from openai import AzureOpenAI

from . import finance
from .config import get_api_key

# Defaults from the hackathon template (main.py); override them in .env.
DEFAULT_ENDPOINT = "https://app-uoaihack2ix6ak.azurewebsites.net"
DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_API_VERSION = "2024-12-01-preview"

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

SYSTEM_PROMPT = """\
You are the explanation layer of ScholarFund AI, an educational prototype
that compares investment strategies for a scholarship fund. You write for
the fund's committee: smart people who are not investment specialists.

Rules:
- Use ONLY the facts and figures in the JSON you receive. Do not invent
  data, returns, holdings, ratings or market events. You may round
  numbers, but do not compute new figures other than simple differences.
- Never say scholarships or capital are guaranteed. Say a strategy
  "passed the tested scenarios" or "failed" a named test.
- If no strategy is recommended, say so plainly first, then use
  sustainable_payouts to explain what payout level would pass.
- Explain every rule that drove the result (risk tolerance, split of
  public markets between bonds/bills and stocks, private equity share,
  reserve, forced-sale avoidance, excise tax, funding tests, ethical
  screen) in plain words, citing the numbers involved.
- If client_inputs.excise_tax_rate is above 0, say explicitly that the tax
  is "modeled on the new 2026 tiered endowment excise tax", give the tier
  rate, and use total_tax_paid / mc_tax_paid_p50 to show its cost. If it is
  0, say the excise tax was switched off.
- If client_inputs.pe_share is above 0, explain that private equity is an
  illustrative assumption (fixed yearly return, locked for pe_lock_years,
  not real holdings), tied to Harvard's situation: over 40% of its fund in
  private equity strained its liquidity, and the model targets 20%. Use
  mc_pe_share_max_p50 to show how the private equity share grows as
  public assets pay scholarships, and the illiquidity failure rates to
  show whether locked money ever caused a missed payment.
- For the ethical screen, name the excluded assets and the companies or
  facts behind each exclusion, and state its coverage limits.
- State the main data limitations given in the JSON (history length,
  proxy data, share of each fund screened, simulation horizon).
- End with the disclaimer from the JSON, in the output language.
- This is not financial advice; do not tell the reader what to buy.

Structure, with short headings:
1. Recommendation
2. Why
3. Risks and stress test
4. Endowment excise tax
5. Private equity and liquidity (only if pe_share is above 0)
6. Ethical screening (only if a Moderate or Strict policy was applied)
7. What would change the result
8. Limitations
"""

# Keys of each available strategy kept in the payload.
STRATEGY_FIELDS = [
    "amounts", "weights", "bond_share_of_public", "stock_share_of_public",
    "fund_substitutions", "uncovered_zones",
    "annualized_return", "annualized_volatility", "maximum_drawdown",
    "expected_total_return", "total_tax_paid", "mc_tax_paid_p50",
    "mc_illiquidity_failure_rate", "stress_illiquidity_failure_rate",
    "mc_pe_share_max_p50",
    "ending_balance", "total_paid", "funding_failure", "first_failure_month",
    "forced_growth_sales", "mc_success_rate", "mc_forced_sale_rate",
    "mc_ending_balance_p5", "mc_ending_balance_p50", "mc_ending_balance_p95",
    "stress_shock", "stress_success_rate", "stress_forced_sale_rate",
    "stress_ending_balance_p50", "failed_checks", "same_allocation_as",
    "mc_real_value_preserved_rate", "mc_real_ending_balance_p50",
]


def _round(value):
    """Round floats recursively so the payload stays short and readable."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: _round(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(item) for item in value]
    return value


def summarize_ethics(reports, policy):
    """Keep only what the explanation needs from the ethics reports."""
    if not reports:
        return None

    summary = {}
    for ticker, report in reports.items():
        flagged = [
            {
                "company": h["name"],
                "weight_in_fund": h["weight"],
                "excluded_activity": h["excluded_activity"],
                "human_rights_commitment": h["human_rights_commitment"],
            }
            for h in report.get("holdings", [])
            if h["excluded_activity"]
            or (
                h["human_rights_commitment"]
                and h["human_rights_commitment"]["value"] != "Yes"
            )
        ]
        summary[ticker] = {
            "fund_type": report["fund_type"],
            "eligible": report["eligible"][policy],
            "reason": report["reasons"][policy],
            "share_of_fund_screened": report.get("screened_fund_weight"),
            "us_government_share": report.get("us_government_share"),
            "flagged_holdings": flagged,
        }
    return summary


def build_llm_payload(result):
    """Compact, JSON-serializable view of an analysis result."""
    inputs = result["client_inputs"]
    context = result["data_context"]

    strategies = {}
    for name, p in result["portfolios"].items():
        if not p["available"]:
            strategies[name] = {"available": False, "reason": p["reason"]}
            continue
        strategies[name] = {"available": True}
        strategies[name].update(
            {key: p[key] for key in STRATEGY_FIELDS if key in p}
        )

    # The payout search is only precise to about $50: round accordingly.
    sustainable = result.get("sustainable_payouts")
    if sustainable:
        sustainable = {
            name: None if payout is None else round(payout / 50) * 50
            for name, payout in sustainable.items()
        }
        sustainable["precision"] = "rounded to the nearest $50"

    payload = {
        "client_inputs": inputs,
        "recommendation": result["recommendation"],
        "recommendation_status": result["recommendation_status"],
        "recommendation_reason": result["recommendation_reason"],
        "sustainable_payouts": sustainable,
        "strategies": strategies,
        "model_rules": {
            "strategies_considered": (
                "Only strategies no riskier than the client's risk "
                "tolerance; the matching one is recommended if it passes, "
                "otherwise the next less risky one that passes."
            ),
            "public_markets": (
                f"{1 - inputs['pe_share']:.0%} of the fund. Bonds and bills "
                "(reserve included) take 70% / 50% / 30% of public markets "
                "for Conservative / Balanced / Growth, stocks the rest; each "
                f"class is always at least {finance.MIN_CLASS_SHARE:.0%}. "
                "Each class is split into zones (weight, funds in order of "
                "preference). An ethically excluded fund is replaced by the "
                "next fund of its zone, an ESG version (fund_substitutions); "
                "a zone with no eligible fund passes its weight to the "
                "other zones (uncovered_zones)."
            ),
            "asset_class_zones": finance.ASSET_CLASSES,
            "annualized_return_scope": (
                "annualized_return, annualized_volatility and "
                "maximum_drawdown cover public markets only (2007-2026 "
                "data); expected_total_return adds the assumed private "
                "equity return."
            ),
            "private_equity": (
                f"{inputs['pe_share']:.0%} of the fund, assumed "
                f"{inputs['pe_annual_return']:.0%} yearly return (below the "
                "11-13% of the last 15 years, deliberately conservative), "
                f"locked for {inputs['pe_lock_years']} years: it cannot pay "
                "scholarships or refill the reserve before. Illustrative "
                "assumption, not real holdings."
            ),
            "reserve": (
                f"{inputs['reserve_years']} years of inflation-indexed "
                f"payouts held in {inputs['reserve_asset']}, refilled "
                "monthly"
            ),
            "forced_sale_avoidance": (
                "Equities are not sold to pay or refill the reserve while "
                f"more than {finance.GROWTH_DRAWDOWN_LIMIT:.0%} below "
                "their peak, unless nothing else is left (counted as a "
                "forced sale)."
            ),
            "funding_tests": (
                "Pay every scholarship over the historical period, and in "
                f"at least {inputs['min_success_rate']:.0%} of "
                f"{inputs['n_simulations']} simulated "
                f"{inputs['horizon_years']}-year paths, both normally and "
                "after a first-month shock."
            ),
            "stress_shocks_by_asset": finance.STRESS_SHOCKS,
            "excise_tax": (
                f"{inputs['excise_tax_rate']:.1%} tax on the gain realized "
                "whenever an asset that has risen in value is sold (to pay "
                "scholarships, refill the reserve or rebalance), modeled on "
                "the new 2026 tiered endowment excise tax (1.4% / 4% / 8% "
                "tiers by endowment per student). Simplified: the real tax "
                "also covers dividends and interest."
            ),
            "real_value": (
                "mc_real_value_preserved_rate is the share of simulated "
                "paths ending with at least the initial capital in today's "
                "dollars; it is reported, not used as a pass/fail test."
            ),
        },
        "data_context": {
            "market_data": context["market_data"],
            "macro": context["macro"],
            "generated_on": context["generated_on"],
            "ethics": summarize_ethics(
                context.get("ethics"), inputs["ethical_policy"]
            ),
        },
        "disclaimer": result["disclaimer"],
    }
    return _round(payload)


def get_client():
    return AzureOpenAI(
        api_key=get_api_key("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", DEFAULT_ENDPOINT),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION),
    )


def explain_result(result, language="English", client=None):
    """
    Ask the LLM to explain an analysis result.

    Returns (explanation_text, payload); the payload is what the model saw.
    """
    payload = build_llm_payload(result)
    client = client or get_client()

    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_MODEL", DEFAULT_MODEL),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Write the explanation in {language}.\n\n"
                    "Analysis results (JSON):\n"
                    + json.dumps(payload, indent=1, default=str)
                ),
            },
        ],
        max_completion_tokens=4096,
    )
    return response.choices[0].message.content, payload


def _payload_numbers(value, found):
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        found.add(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _payload_numbers(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _payload_numbers(item, found)
    elif isinstance(value, str):
        for number in re.findall(r"\d+(?:\.\d+)?", value):
            found.add(float(number))
    return found


def normalize_number_format(text):
    """
    Rewrite numbers in English format so they can be parsed, whatever the
    output language: "8 120" -> "8120", "38,89 %" -> "38.89 %".
    A comma followed by exactly three digits is a thousands separator
    ("5,000"); any other comma between digits is a decimal comma.
    """
    text = re.sub(r"[\u00a0\u202f]", " ", text)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"(\d) (\d{3})(?!\d)", r"\1\2", text)
    return re.sub(r"(\d),(\d{1,2}|\d{4,})(?!\d)", r"\1.\2", text)


def unverified_numbers(text, payload, relative_tolerance=0.02):
    """
    Numbers in the explanation that match nothing in the payload.

    Percentages are compared with both the raw value and value x 100
    (rates are stored as decimals), ignoring signs (the text may write a
    loss as "-12%" or "a 12% decline"). Small counts (<= 31) and years are
    ignored. This is a safety net, not proof that the text is correct.
    """
    known = {abs(value) for value in _payload_numbers(payload, set())}
    candidates = known | {value * 100 for value in known}

    flagged = []
    text = normalize_number_format(text)
    for match in re.finditer(r"\$?\d[\d,]*(?:\.\d+)?\s?(?:%|k\b)?", text):
        token = match.group(0).strip()
        number = float(re.sub(r"[^\d.]", "", token) or 0)
        if token.endswith("k"):
            number *= 1_000
        if number <= 31 and "%" not in token and "$" not in token:
            continue
        if 1900 <= number <= 2100 and "%" not in token and "$" not in token:
            continue

        tolerance = max(abs(number) * relative_tolerance, 0.06)
        if not any(abs(number - value) <= tolerance for value in candidates):
            flagged.append(token)
    return flagged


if __name__ == "__main__":
    from .analysis import run_analysis

    result = run_analysis(
        risk_tolerance="Growth",
        ethical_policy="Moderate",
        annual_payout=5_000,
        initial_capital=100_000,
    )
    text, payload = explain_result(result, language="English")
    flagged = unverified_numbers(text, payload)
    check = (
        "Numbers not found in the data: " + ", ".join(flagged)
        if flagged else "Every number in the explanation matches the data."
    )
    print(text)
    print("\n---\n" + check)

    REPORTS_DIR.mkdir(exist_ok=True)
    date = result["data_context"]["generated_on"]
    report_file = REPORTS_DIR / f"explanation_{date}.md"
    report_file.write_text(f"{text}\n\n---\n\n_{check}_\n")
    print(f"Saved to {report_file.name} in {REPORTS_DIR.name}/")
