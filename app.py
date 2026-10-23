"""
app.py - OWNER: Person 3 (App builder)
The Streamlit user interface. Imports the engine results from model.py and the AI from llm.py.
Run with: streamlit run app.py
Educational hackathon project. Not financial advice.
"""
import pandas as pd
import streamlit as st

from webapp.llm import (
    ask_llm, SYSTEM_PROMPT, MEMO_PROMPT, build_context,
    split_action, sanitize,
)
from scholarfund.llm_explainer import explain_result, unverified_numbers
from webapp.model import (
    HARVARD, ASSET_NAMES, ETHICS, ETHICS_LABELS, PROFILES, DEFAULTS,
    FRED_INFLATION, PE_CHOICES, TAX_TIERS_PCT,
    run_scenario, market_snapshot,
)

st.set_page_config(
    page_title="Harvard Scholarship AI Analyst",
    page_icon="🎓",
    layout="wide",
)

# ---------- visual styling only ----------
# ---------- visual styling only ----------
st.markdown(
    """
    <style>
        .block-container {
            max-width: 1440px;
            padding-top: 5rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3 {
            letter-spacing: -0.025em;
        }

        h1 {
            font-weight: 750;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid #E4E7EC;
        }

        [data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem;
        }

        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E4E7EC;
            border-radius: 12px;
            padding: 1rem;
            height: 100%;
            box-sizing: border-box;
            box-shadow: 0 2px 6px rgba(16, 24, 40, 0.04);
        }

        [data-testid="stMetricLabel"] {
            color: #667085;
        }

        [data-testid="stMetricValue"] {
            font-size: clamp(1.3rem, 2vw, 1.9rem);
            font-weight: 700;
            letter-spacing: -0.025em;
        }

        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 1rem;
            border-bottom: 1px solid #E4E7EC;
        }

        [data-testid="stTabs"] [data-baseweb="tab"] {
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
            font-weight: 600;
        }

        [data-testid="stButton"] button {
            min-height: 2.6rem;
            border-radius: 8px;
            font-weight: 600;
        }

        [data-testid="stAlert"] {
            border-radius: 10px;
        }

        .crimson-kicker {
            color: #A51C30;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .crimson-rule {
            width: 46px;
            height: 4px;
            background: #A51C30;
            border-radius: 4px;
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- session state + settings the AI asked to change ----------
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)
st.session_state.setdefault("messages", [])

pending = st.session_state.pop("pending", None)
if pending:
    for k, v in pending.items():
        st.session_state[k] = v


def set_state(**kw):
    for k, v in kw.items():
        st.session_state[k] = v


# ---------- sidebar controls ----------
with st.sidebar:
    st.markdown(
        '<div class="crimson-kicker">Scholarship strategy</div>',
        unsafe_allow_html=True,
    )
    st.header("Scenario controls")
    st.caption("Adjust assumptions to update the analysis across all tabs.")

    st.subheader("Portfolio")
    st.radio("Risk profile", list(PROFILES), key="risk", horizontal=True)
    st.radio(
        "Ethical screen", ETHICS, key="ethics", horizontal=True,
        help=" · ".join(f"{k}: {v}" for k, v in ETHICS_LABELS.items()),
    )
    st.caption(ETHICS_LABELS[st.session_state["ethics"]])
    st.radio(
        "Private equity (illiquid)", PE_CHOICES, key="pe", horizontal=True,
        format_func=lambda v: {0: "None", 20: "20% (target)",
                               40: "40% (Harvard today)"}[v],
        help="Illustrative: assumed 9% a year, locked 7 years. The rest "
             "of the fund is in public markets, split by risk profile.",
    )

    st.divider()
    st.subheader("Gift and payout")
    st.number_input(
        "Gift size ($)", 10_000, 10_000_000,
        step=10_000, key="gift",
    )
    st.slider(
        "Annual payout rate (%)", 2.0, 8.0,
        key="payout", step=0.1,
    )
    st.caption(
        f"= ${st.session_state['gift'] * st.session_state['payout'] / 100:,.0f} "
        "in year 1, then indexed on inflation"
    )

    st.divider()
    st.subheader("Planning assumptions")
    st.toggle(
        "Endowment excise tax", key="tax_on",
        help="Paid on the gain realized when the fund sells assets that "
             "have risen in value. Modeled on the new 2026 tiered tax: "
             + " / ".join(f"{v:g}%" for v in TAX_TIERS_PCT.values() if v)
             + f" tiers; Harvard pays {HARVARD['tax_new']:g}%.",
    )
    st.slider(
        "Excise tax rate on realized gains (%)",
        0.0, 10.0, key="tax", step=0.1,
        disabled=not st.session_state["tax_on"],
    )
    st.slider("Horizon (years)", 5, 40, key="years")
    st.slider(
        "Inflation (%)", 0.0, 6.0, key="infl", step=0.1,
        help=f"For reference, the 10-year US CPI average (FRED) is {FRED_INFLATION}%.",
    )

    st.divider()
    st.caption("Educational hackathon project. Not financial advice.")

S = {k: st.session_state[k] for k in DEFAULTS}


@st.cache_data(show_spinner="Running the scenario on market data…")
def cached_scenario(settings_items):
    return run_scenario(dict(settings_items))


R = cached_scenario(tuple(sorted(S.items())))
result = R["result"]
portfolio = R["portfolio"]
shown = R["shown_strategy"]


def pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def usd(x):
    return "n/a" if x is None else f"${x:,.0f}"


def md(text):
    """Escape $ so Streamlit's Markdown does not read amounts as LaTeX."""
    return text.replace("$", "\\$")


# ---------- header ----------
st.markdown('<div class="crimson-kicker">Harvard scholarship endowment</div>',
            unsafe_allow_html=True)
st.title("Scholarship AI Analyst")
st.markdown('<div class="crimson-rule"></div>', unsafe_allow_html=True)

if R["recommended"]:
    same = portfolio.get("same_allocation_as")
    note = (
        f" After the {S['ethics']} screen, its allocation is the same as "
        f"{same}: " + ", ".join(
            f"{ASSET_NAMES[t]} {w:.0%}" for t, w in portfolio["weights"].items()
        ) + "."
        if same else ""
    )
    st.success(md(
        f"**Recommended: {shown}.** {result['recommendation_reason']}{note}"
    ))
elif not shown:
    reasons = {
        p["reason"] for p in result["portfolios"].values()
        if not p["available"] and "Riskier" not in p["reason"]
    }
    st.warning(md(
        f"**No strategy is available with the {S['ethics']} screen.** "
        + " ".join(sorted(reasons))
        + " Try a less strict ethical screen."
    ))
else:
    payouts = result.get("sustainable_payouts") or {}
    best = max((p for p in payouts.values() if p), default=None)
    hint = (
        f" The highest payout passing every test is about "
        f"**{usd(best)} per year** ({best / S['gift']:.1%} of the gift)."
        if best else ""
    )
    st.warning(md(
        f"**No strategy passed every funding test** at "
        f"{usd(R['annual_payout'])} per year.{hint} "
        + (f"Figures below show **{shown}**, the client's profile, for reference."
           if shown else "")
    ))

if portfolio:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Strategy shown", shown)
    c2.metric(
        "Success rate",
        pct(portfolio["mc_success_rate"]),
        help=f"Share of 1,000 simulated {S['years']}-year paths (2007-2026 market data) paying every scholarship.",
    )
    c3.metric(
        "After a crash",
        pct(portfolio["stress_success_rate"]),
        help=f"Same paths with a {portfolio['stress_shock']:.1%} shock in month 1.",
    )
    c4.metric(
        "Keeps real value",
        pct(portfolio["mc_real_value_preserved_rate"]),
        help="Share of paths ending with at least the gift in today's dollars.",
    )
    c5.metric(
        f"Scholarships over {S['years']} y",
        usd(R["total_promised"]),
        help="Total scholarships to pay over the horizon, inflation "
             "indexation included.",
    )

tab_plan, tab_sim, tab_liq, tab_tax, tab_ethics, tab_ai, tab_data = st.tabs([
    "Allocation", "Simulation", "Liquidity", "Endowment tax", "Ethics",
    "AI analyst", "Data & assumptions",
])

# ---------- Allocation ----------
with tab_plan:
    if not portfolio:
        st.info("No strategy is available with these settings.")
    else:
        left, right = st.columns([3, 2])
        with left:
            st.subheader(f"{shown}: where the money goes")
            alloc = pd.Series(R["alloc"], name="USD")
            st.bar_chart(alloc, horizontal=True, color="#A51C30")
            st.caption(md(
                f"Includes a {usd(R['reserve'])} scholarship reserve "
                "(two years of payouts) held in Treasury bills. Public "
                f"markets: {portfolio['bond_share_of_public']:.0%} bonds and "
                f"bills, {portfolio['stock_share_of_public']:.0%} stocks."
                + (f" Private equity ({S['pe']}%) is locked for 7 years."
                   if S["pe"] else "")
            ))
            for zone, sub in portfolio["fund_substitutions"].items():
                st.caption(
                    f"{zone}: {sub['excluded']} is excluded by the "
                    f"{S['ethics']} screen, replaced by its ESG version "
                    f"{sub['replaced_by']}."
                )
            if portfolio["uncovered_zones"]:
                st.caption(
                    "No eligible fund for: "
                    + ", ".join(portfolio["uncovered_zones"])
                    + ". Their share goes to the other funds of the class."
                )
        with right:
            st.subheader("Allocation")
            table = pd.DataFrame({
                "Asset class": list(R["alloc"]),
                "Amount": [usd(v) for v in R["alloc"].values()],
                "Share": [f"{v / S['gift']:.0%}" for v in R["alloc"].values()],
            })
            st.dataframe(table, hide_index=True, width="stretch")
            if portfolio.get("failed_checks"):
                st.markdown("**Tests failed**")
                for check in portfolio["failed_checks"]:
                    st.markdown(f"- {check}")

# ---------- Simulation ----------
with tab_sim:
    st.subheader("Strategies compared")
    rows = []
    for name, p in result["portfolios"].items():
        if not p["available"]:
            rows.append({"Strategy": name, "Status": p["reason"]})
            continue
        status = "✅ passes" if not p["failed_checks"] else "❌ fails"
        if p.get("same_allocation_as"):
            status += f" (same as {p['same_allocation_as']})"
        rows.append({
            "Strategy": name,
            "Status": status,
            "Bonds / stocks": (
                f"{p['bond_share_of_public']:.0%} / "
                f"{p['stock_share_of_public']:.0%}"
            ),
            "Public return / yr": pct(p["annualized_return"]),
            "With PE / yr": pct(p["expected_total_return"]),
            "Worst fall": pct(p["maximum_drawdown"]),
            "Success": pct(p["mc_success_rate"]),
            "Success after crash": pct(p["stress_success_rate"]),
            "Median end value": usd(p["mc_ending_balance_p50"]),
            "Keeps real value": pct(p["mc_real_value_preserved_rate"]),
            "Tax paid (median)": usd(p["mc_tax_paid_p50"]),
        })
    st.dataframe(pd.DataFrame(rows).fillna(""), hide_index=True, width="stretch")

    payouts = result.get("sustainable_payouts")
    if payouts:
        st.markdown("**Highest annual payout passing every test**")
        st.dataframe(
            pd.DataFrame({
                "Strategy": list(payouts),
                "Payout / yr": [usd(v) for v in payouts.values()],
                "Rate": [pct(v / S["gift"]) if v else "n/a"
                         for v in payouts.values()],
            }),
            hide_index=True,
        )

    histories = {
        name: p["balance_history"]
        for name, p in result["portfolios"].items() if p["available"]
    }
    if histories:
        st.subheader("If the fund had started in 2007")
        st.line_chart(pd.DataFrame(histories))
        st.caption(
            "Total fund value month by month on real market data, paying "
            "the scholarships. Simulated paths use the same history."
        )

# ---------- Ethics ----------
with tab_ethics:
    reports = result["data_context"]["ethics"]
    if not reports:
        st.info("No ethical screen applied (Standard). Choose Moderate or "
                "Strict in the sidebar to screen the funds.")
    else:
        st.subheader(f"{S['ethics']} screen: {ETHICS_LABELS[S['ethics']]}")
        for ticker, report in reports.items():
            ok = report["eligible"][S["ethics"]]
            icon = "✅" if ok else "🚫"
            with st.expander(
                f"{icon} {ticker} — {ASSET_NAMES.get(ticker, ticker)}",
                expanded=not ok,
            ):
                st.markdown(md(report["reasons"][S["ethics"]]))
                if report["holdings"]:
                    st.dataframe(pd.DataFrame([{
                        "Company": h["name"],
                        "Weight": f"{h['weight']:.1%}",
                        "Sector": h["sector"],
                        "Excluded activity": h["excluded_activity"] or "",
                        "Human rights commitment": (
                            h["human_rights_commitment"]["value"]
                            if h["human_rights_commitment"] else "not found"
                        ),
                    } for h in report["holdings"]]), hide_index=True,
                        width="stretch")
        st.caption(
            "Top holdings from Yahoo Finance; human rights commitments from "
            "Wikirate (World Benchmarking Alliance). Only the largest "
            "holdings are screened; a missing answer never counts as a pass."
        )

# ---------- Liquidity (private equity) ----------
with tab_liq:
    other = R["pe_compare"]["portfolio"]
    st.subheader(f"Private equity: {S['pe']}% vs {R['pe_compare_pct']}%")
    st.caption(
        f"Harvard holds over {HARVARD['pe_share_today']}% of its endowment "
        "in private equity, which strained its liquidity; the model targets "
        "20%. Illustrative assumption: 9% a year (below the 11-13% of the "
        "last 15 years), locked for 7 years, so scholarships and the "
        "reserve can only be funded from public markets."
    )
    if portfolio and other:
        def delta(key, scale=100, unit=" pts"):
            return f"{(portfolio[key] - other[key]) * scale:+.1f}{unit}"

        l1, l2, l3, l4 = st.columns(4)
        l1.metric(
            "PE share at its peak", pct(portfolio["mc_pe_share_max_p50"]),
            delta=delta("mc_pe_share_max_p50"), delta_color="inverse",
            help="Median, over simulated paths, of the highest share of the "
                 "fund held in private equity: it grows as public assets "
                 "pay the scholarships.",
        )
        l2.metric(
            "Missed payment, money locked",
            pct(portfolio["stress_illiquidity_failure_rate"]),
            delta=delta("stress_illiquidity_failure_rate"),
            delta_color="inverse",
            help="After a crash: share of paths where a scholarship was "
                 "missed while private equity still held the money.",
        )
        l3.metric(
            "After a crash", pct(portfolio["stress_success_rate"]),
            delta=delta("stress_success_rate"),
        )
        l4.metric(
            "Keeps real value", pct(portfolio["mc_real_value_preserved_rate"]),
            delta=delta("mc_real_value_preserved_rate"),
        )
        st.caption(f"Deltas compare with {R['pe_compare_pct']}% private "
                   "equity, everything else unchanged.")

        if S["pe"] or R["pe_compare_pct"]:
            share = pd.DataFrame({
                f"{S['pe']}% PE": portfolio["pe_history"]
                / portfolio["balance_history"] * 100,
                f"{R['pe_compare_pct']}% PE": other["pe_history"]
                / other["balance_history"] * 100,
            })
            st.markdown("**Share of the fund in private equity (%), if the "
                        "fund had started in 2007**")
            st.line_chart(share, y_label="% of the fund")
            st.caption(
                "As scholarships are paid from public markets, private "
                "equity becomes a bigger part of the fund (the 'denominator "
                "effect'). After 7 years it can be sold and the share "
                "levels off. Try a 6-7% payout to see locked money cause "
                "missed payments after a crash."
            )
        st.caption(
            "Private equity's fixed assumed return makes it look smooth and "
            "attractive; real private equity is riskier than shown here."
        )

# ---------- Endowment tax ----------
with tab_tax:
    other = R["tax_compare"]["portfolio"]
    now, alt = R["tax_pct"], R["tax_compare_pct"]
    label = lambda t: f"{t:g}% tax" if t else "no tax"
    st.subheader(f"Endowment excise tax: {label(now)} vs {label(alt)}")
    st.caption(md(
        "Modeled on the new 2026 tiered endowment excise tax ("
        + " / ".join(f"{v:g}%" for v in TAX_TIERS_PCT.values() if v)
        + f" tiers). Harvard is in the {HARVARD['tax_new']:g}% tier (it was "
        f"{HARVARD['tax_old']}% before). Here the tax is paid on the gain "
        "realized each time the fund sells an asset that has risen in "
        "value; the real tax also covers dividends and interest."
    ))
    if portfolio and other:
        t1, t2, t3 = st.columns(3)
        t1.metric(
            f"Tax paid over {S['years']} y (median)",
            usd(portfolio["mc_tax_paid_p50"]),
            delta=f"{portfolio['mc_tax_paid_p50'] - other['mc_tax_paid_p50']:+,.0f} $",
            delta_color="inverse",
        )
        t2.metric(
            f"Median value after {S['years']} y",
            usd(portfolio["mc_ending_balance_p50"]),
            delta=f"{portfolio['mc_ending_balance_p50'] - other['mc_ending_balance_p50']:+,.0f} $",
        )
        t3.metric(
            "Keeps real value", pct(portfolio["mc_real_value_preserved_rate"]),
            delta=f"{(portfolio['mc_real_value_preserved_rate'] - other['mc_real_value_preserved_rate']) * 100:+.1f} pts",
        )
        alt_rec = R["tax_compare"]["result"]["recommendation"]
        st.markdown(
            f"With {label(alt)}, the recommendation would be "
            f"**{alt_rec or 'none'}**; with the current settings it is "
            f"**{result['recommendation'] or 'none'}**."
        )
        st.caption(md(
            f"Harvard facts (FY2026, to verify): endowment "
            f"${HARVARD['endowment_bn']}bn, financial aid ${HARVARD['aid_m']}m."
        ))

# ---------- AI analyst ----------
with tab_ai:
    context = build_context(S, R)
    language = st.radio("Language", ["English", "French"], horizontal=True)

    b1, b2 = st.columns(2)
    if b1.button("Write committee memo", width="stretch"):
        with st.spinner("Writing the memo…"):
            st.session_state["memo"] = ask_llm([
                {"role": "system", "content": SYSTEM_PROMPT + context},
                {"role": "user", "content": MEMO_PROMPT + f" Write in {language}."},
            ])
    if b2.button("Full explanation (numbers checked)", width="stretch"):
        with st.spinner("Explaining the results…"):
            try:
                text, payload = explain_result(result, language=language)
                st.session_state["explanation"] = (
                    text, unverified_numbers(text, payload)
                )
            except Exception as e:  # noqa
                st.session_state["explanation"] = (f"⚠️ AI call failed: {e}", [])

    if st.session_state.get("memo"):
        with st.container(border=True):
            st.markdown(md(st.session_state["memo"]))
    if st.session_state.get("explanation"):
        text, flagged = st.session_state["explanation"]
        with st.container(border=True):
            st.markdown(md(text))
            if flagged:
                st.caption("Numbers not found in the data (check by hand): "
                           + ", ".join(flagged))
            else:
                st.caption("✓ Every number matches the engine's results.")

    st.divider()
    st.subheader("Ask the analyst")
    st.caption('Try: "What if we lowered the payout to 3.5%?", '
               '"Show me Harvard\'s 40% private equity" or '
               '"Switch the excise tax to the 8% tier."')
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(md(msg["content"]))

    question = st.chat_input("Ask about the scenario or ask to change a setting")
    if question:
        st.session_state["messages"].append({"role": "user", "content": question})
        reply = ask_llm(
            [{"role": "system", "content": SYSTEM_PROMPT + context}]
            + st.session_state["messages"][-10:]
        )
        text, action = split_action(reply)
        changes = sanitize(action) if action else {}
        if changes:
            text += "\n\n_Applied: " + ", ".join(
                f"{k} = {v}" for k, v in changes.items()) + "_"
            st.session_state["pending"] = changes
        st.session_state["messages"].append({"role": "assistant", "content": text})
        st.rerun()

# ---------- Data & assumptions ----------
with tab_data:
    market = result["data_context"]["market_data"]
    macro = result["data_context"]["macro"]
    st.subheader("Where the numbers come from")
    st.markdown(
        f"- **Market data**: Yahoo Finance, {market['first_month']} to "
        f"{market['last_month']} ({market['n_months']} months)"
        + "".join(f"; {a} uses {p['proxy']} before {p['until']}"
                  for a, p in market["proxies"].items())
        + "\n"
        f"- **Inflation used**: {S['infl']:.1f}% (FRED 10-year CPI average: "
        f"{macro.get('fred_inflation_rate', macro['inflation_rate']):.2%})\n"
        "- **Ethics**: Yahoo Finance top holdings + Wikirate\n"
        f"- **Simulation**: 1,000 paths of {S['years']} years resampled from "
        "history; stress = shock in month 1 (equities -40%, bonds -10%, "
        "private equity -30%)\n"
        "- **Private equity**: illustrative 9% a year, locked 7 years "
        "(no market data)\n"
        "- **Pass rule**: pay every scholarship in history and in ≥90% of "
        "paths, with and without the shock"
    )
    snap = market_snapshot()
    if snap:
        st.markdown("**Last 12 months**")
        cols = st.columns(len(snap))
        for col, (ticker, ret) in zip(cols, snap.items()):
            col.metric(ASSET_NAMES.get(ticker, ticker), f"{ret:+.1f}%")
    st.caption("Educational hackathon project. Not financial advice. "
               "Past market data does not predict future returns.")
