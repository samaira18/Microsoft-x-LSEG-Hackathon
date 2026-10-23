"""
llm.py  -  OWNER: Person 1 (API & AI)
Connects to the hackathon Azure OpenAI endpoint (through llm_explainer),
holds the chat prompts, and parses "change a setting" actions from the AI.
No Streamlit in here.
Educational hackathon project. Not financial advice.
"""
import json
import os
import re

from scholarfund.config import MissingApiKeyError
from scholarfund.llm_explainer import DEFAULT_MODEL, get_client
from webapp.model import DEFAULTS, ETHICS, HARVARD, PE_CHOICES, PROFILES

MODEL = os.getenv("AZURE_OPENAI_MODEL", DEFAULT_MODEL)


def ask_llm(messages):
    """Call the model. Never crashes the demo - returns a warning string instead."""
    try:
        client = get_client()
    except MissingApiKeyError:
        return "⚠️ AI not connected yet. Add AZURE_OPENAI_API_KEY to your .env file, then restart the app."
    try:
        resp = client.chat.completions.create(model=MODEL, messages=messages, max_completion_tokens=4096)
        return resp.choices[0].message.content
    except Exception as e:  # noqa
        return f"⚠️ AI call failed: {e}"


# ---------------------------------------------------------------------
# PROMPTS  (Person 1: tune these in the playground first, then paste here)
# ---------------------------------------------------------------------
SYSTEM_PROMPT = """You are the AI investment analyst for a Harvard scholarship endowment gift.
Your client's objectives: (1) fund scholarships every year, (2) preserve the real (inflation-adjusted) value of the gift,
(3) respect ethical screens. Be concise, specific and plain-English (max ~150 words unless asked for more).
RULES: Use ONLY numbers from the CONTEXT below - never invent figures. If a number is not in CONTEXT, say so.
Never say payments or capital are guaranteed: say a strategy "passed" or "failed" the tested scenarios.
When the excise tax is on, say it is modeled on the new 2026 tiered endowment excise tax (1.4% / 4% / 8% tiers;
Harvard is in the 8% tier) and quote its cost from CONTEXT. Private equity is an illustrative assumption
(fixed 9% a year, locked 7 years): Harvard holds over 40% in private equity, which strained its liquidity,
and the model targets 20%; use the PE comparison in CONTEXT to show the liquidity trade-off.
Explain trade-offs. This is an educational hackathon project, not financial advice.
If the user asks to CHANGE a setting, answer briefly AND end your reply with one final line exactly like:
ACTION: {"risk": "Growth", "ethics": "Strict", "pe": 40, "tax_on": true, "tax": 8, "payout": 4.5, "years": 10, "gift": 100000, "infl": 3.0}
including ONLY the keys that change. risk must be Conservative, Balanced or Growth; ethics must be
Standard, Moderate or Strict; pe must be 0, 20 or 40; tax_on is true or false; tax, payout and infl are percentages.
CONTEXT:
"""

MEMO_PROMPT = ("Write a recommendation memo for the endowment committee: 1) Recommendation (or, if no strategy passed, "
               "the payout level that would pass) with exact $ by asset class, private equity included; "
               "2) Three reasons, each citing a number; 3) Impact of the endowment excise tax, modeled on the new "
               "2026 tiered tax (compare with the tax comparison in CONTEXT); 4) Liquidity: what the private equity "
               "share does, compared with Harvard's 40% today; 5) Two key risks; 6) What would change our mind. "
               "Under 300 words.")


def build_context(settings, R):
    """Turns the current settings + engine results into the text the AI is allowed to use."""
    def summary(compare):
        p = compare["portfolio"]
        if not p:
            return None
        return {
            "recommendation": compare["result"]["recommendation"],
            "mc_success_rate": p["mc_success_rate"],
            "stress_success_rate": p["stress_success_rate"],
            "mc_ending_balance_p50": round(p["mc_ending_balance_p50"]),
            "mc_real_value_preserved_rate": p["mc_real_value_preserved_rate"],
            "mc_tax_paid_p50": round(p["mc_tax_paid_p50"]),
            "mc_pe_share_max_p50": p["mc_pe_share_max_p50"],
            "stress_illiquidity_failure_rate": p["stress_illiquidity_failure_rate"],
        }

    return json.dumps({
        "client": "Harvard University scholarship endowment gift",
        "harvard_facts_FY2026": HARVARD,
        "settings": {k: settings[k] for k in DEFAULTS},
        "annual_payout_usd": round(R["annual_payout"]),
        "strategy_shown": R["shown_strategy"],
        "strategy_shown_is_recommended": R["recommended"],
        "allocation_usd_by_asset_class": R["alloc"],
        "scholarship_reserve_usd": round(R["reserve"]),
        "scholarships_promised_over_horizon_usd": round(R["total_promised"]),
        "excise_tax_pct_applied": R["tax_pct"],
        "same_strategy_with_tax_at": {
            "tax_pct": R["tax_compare_pct"], **(summary(R["tax_compare"]) or {}),
        },
        "same_strategy_with_private_equity_at": {
            "pe_pct": R["pe_compare_pct"], **(summary(R["pe_compare"]) or {}),
        },
        "engine_results": R["payload"],
    }, indent=1, default=str)


def split_action(text):
    """Separates the human-readable reply from the trailing ACTION: {...} line."""
    m = re.search(r"ACTION:\s*(\{.*\})\s*$", text.strip(), re.S)
    if not m:
        return text, None
    try:
        return text[:m.start()].strip(), json.loads(m.group(1))
    except Exception:  # noqa
        return text[:m.start()].strip(), None


def sanitize(action):
    """Only accept safe, in-range values from the AI."""
    out = {}
    try:
        if action.get("risk") in PROFILES:
            out["risk"] = action["risk"]
        if action.get("ethics") in ETHICS:
            out["ethics"] = action["ethics"]
        if action.get("pe") in PE_CHOICES:
            out["pe"] = int(action["pe"])
        if isinstance(action.get("tax_on"), bool):
            out["tax_on"] = action["tax_on"]
        if "tax" in action:
            out["tax"] = float(min(max(float(action["tax"]), 0), 10))
        if "payout" in action:
            out["payout"] = float(min(max(float(action["payout"]), 2), 8))
        if "infl" in action:
            out["infl"] = float(min(max(float(action["infl"]), 0), 6))
        if "years" in action:
            out["years"] = int(min(max(int(action["years"]), 5), 40))
        if "gift" in action:
            out["gift"] = int(min(max(int(action["gift"]), 10_000), 10_000_000))
    except Exception:  # noqa
        pass
    return out
