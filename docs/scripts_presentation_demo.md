# Scholarship AI Analyst — Scripts

Two scripts: the **presentation** (17 slides, about 7 minutes) and the
**live demo** (about 4 minutes). The split between speakers is a
suggestion; change it freely.

| Speaker | Slides |
|---|---|
| Samaira | 1–3 · team, client, endowments in one minute |
| Morgan | 4–7 · the problems and the question |
| Charlotte | 8–10 · the solution, ethics, how scholarships are protected |
| Lakshman | 11–12 · data sources and how the model learns |
| Saikiran | 13–17 · results, AI analyst, limits, hand-over to the demo |

---

## Part 1 — Presentation script

### 1. Cover · *Samaira* (20 s)

> Hi everyone. We are Samaira, Morgan, Charlotte, Lakshman and Saikiran.
> We chose Track 3, and our client is Harvard University.
> We built the **Scholarship AI Analyst**: a tool that helps Harvard pay
> every scholarship, even when markets fall.

### 2. Our client · *Samaira* (30 s)

> Harvard runs the largest university endowment in the United States:
> about 57 billion dollars, after an 11.9% return last fiscal year.
> This money matters for students: the endowment pays for more than a
> third of Harvard's budget, and it's what makes tuition free for families
> earning under 200,000 dollars a year.
> So the endowment has one promise to keep: pay out, every single year.

### 3. Endowments in one minute · *Samaira* (30 s)

> Quick reminder of how an endowment works. A donor gives a gift once.
> Harvard invests it, and every year a small share is paid out — for
> example as a scholarship.
> Take a 100,000-dollar gift with a 4% payout: that's 4,000 dollars of aid
> a year, rising with inflation.
> And there's one golden rule: the investments must earn at least the
> payout plus inflation. Otherwise, the gift slowly shrinks.

### 4. Problem 1 · Locked-up money · *Morgan* (35 s)

> Here's Harvard's first problem. More than 40% of its endowment is in
> private equity — stakes in private companies that can't be sold
> quickly.
> When markets crash, scholarships still have to be paid. Since private
> equity is locked, Harvard has to sell its stocks and bonds instead —
> at the worst moment, at a loss.
> And it gets worse over time: every payout shrinks the liquid part, so
> the locked share keeps growing.

### 5. Problem 2 · A heavier tax · *Morgan* (30 s)

> Second problem: the federal tax on endowments jumped from 1.4% to 8%
> for the richest universities, and Harvard is in that top tier.
> It hits realized gains: every time Harvard sells an asset that has grown
> in value to pay a scholarship, 8% of the gain goes to tax.
> So a forced sale in a bad year now costs twice.

### 6. Why Harvard needs an analyst · *Morgan* (30 s)

> Put together, Harvard faces harder choices, under closer watch.
> There's less room for error: a wrong payout decision costs more.
> Students are watching: recent protests asked Harvard to divest from
> weapons makers and fossil fuels.
> And the investment committee needs to understand *why* a strategy is
> chosen — not just get a number from a black box.

### 7. The question · *Morgan* (15 s)

> So our whole tool answers one question: **how much can we pay out every
> year, without being forced to sell at the wrong time** — while keeping
> the gift's value, paying the new tax, and respecting ethical screens?

### 8. Our solution · *Charlotte* (35 s)

> Our answer is a web app with an AI analyst, built for the endowment
> committee.
> On one side, the committee chooses: how much risk to take, how strict
> the ethical screen is, how much goes into private equity, the yearly
> payout, the tax and inflation.
> On the other side, it gets a clear verdict — the strategy that pays
> every scholarship, or the payout that would work — where each dollar
> goes, how the plan holds up in a crash, and a memo and a chat with the
> AI analyst.

### 9. Ethical screening · *Charlotte* (30 s)

> Because of the student protests, we built ethics in from the start.
> There are three levels. Moderate excludes any fund whose largest
> holdings include fossil fuels, weapons or tobacco. Strict also requires
> public human rights commitments.
> For example, Shell is one of the top holdings of the international stock
> fund, so the app swaps it for an ESG fund covering the same markets — and
> the money stays diversified.

### 10. Never forced to sell · *Charlotte* (35 s)

> Behind the verdict, four simple rules protect the scholarships.
> Private equity is capped at 20% — half of today's level.
> Two years of scholarships are always kept in cash.
> Stocks are never sold while they're down more than 10%: cash and bonds
> pay instead.
> And the risk profile only changes the mix between bonds and stocks —
> always at least 30% of each.

### 11. Data sources · *Lakshman* (30 s)

> Everything runs on free, public data, refreshed every day.
> Yahoo Finance gives us daily prices for seven funds since 2007, and what
> each fund holds. FRED, from the US Federal Reserve, gives us inflation.
> Wikirate is an open database on how companies behave, for example on
> human rights. And Azure OpenAI powers the AI analyst.

### 12. How the model learns · *Lakshman* (40 s)

> We don't guess future returns: the model learns from 19 years of real
> markets — 232 months, including the 2008 crisis and the 2020 crash.
> It reshuffles that history into 1,000 possible 10-year futures, then
> replays every one of them with a market crash in the very first month.
> And since the data is refreshed daily, it always reflects the latest
> market.
> The AI analyst is not trained on opinions: it only reads today's
> results, and every number it writes is checked against them.

### 13. Result · Liquidity · *Saikiran* (35 s)

> Here's what this shows for Harvard. Imagine a crash, and a payout of 6%
> or 7% a year.
> With 40% in private equity — roughly Harvard today — scholarships are
> missed in 9% of our futures at 6%, and in 28% at 7%, even though the
> money exists: it's just locked.
> At 20%, that drops to 0% and under 2%.
> And even at a normal 4% payout, a 40% private equity share climbs to
> about two thirds of the fund.

### 14. Result · The tax · *Saikiran* (25 s)

> The tax tells the same story. On a 100,000-dollar gift over 10 years, a
> calm plan pays about 370 dollars of tax. A plan close to Harvard today —
> 8% tax, 6% payout, 40% private equity — pays about 1,900 dollars. Five
> times more, because the fund has to sell more, at a higher rate.

### 15. The AI analyst · *Saikiran* (30 s)

> Finally, the AI analyst turns all of this into plain language: a memo
> for the committee or a full explanation, in English or French.
> It can only use the engine's numbers, and we check every figure it
> writes. In the chat, you can also change the scenario just by asking —
> for example, "show me Harvard's 40% private equity".

### 16. Honest limits · *Saikiran* (25 s)

> We want to be clear about the limits. Private equity uses a steady
> assumed return, so the real thing is riskier. The tax only covers
> realized gains. The ethical screen sees each fund's top 10 holdings. And
> the past doesn't predict the future.
> Next, we'd validate the thresholds with the committee and model private
> equity more realistically.

### 17. Close · *Saikiran* (10 s)

> In one sentence: pick a scenario, read the verdict, ask the analyst why.
> Let us show you.

---

## Part 2 — Demo script

### Before you start (5 minutes before)

- Launch the app: `streamlit run app.py`, open http://localhost:8501.
- **Warm it up**: click through every step below once. Results are kept
  in memory for the day, so the live demo is instant.
- Check the AI works: send one chat message. Keep a pre-generated memo
  open in another tab as a backup.
- Reset to the default settings: reload the page.
- Zoom the browser to about 125% so the room can read it.

### Step 1 · The calm scenario (40 s)

**Show:** the page as it opens (Balanced, Moderate, 20% private equity,
2% tax, 4% payout).

> This is what the committee sees first. Balanced profile, moderate ethical
> screen, 20% private equity, 4% payout.
> Green banner: Balanced is recommended. In our 1,000 futures it pays every
> scholarship — **100%**, even after a crash — and in **44%** of them the
> gift also keeps its value after inflation.

**Click:** *Allocation* tab.

> Here is where every dollar goes. And notice this line: the international
> stock fund was excluded by the ethical screen and replaced by its ESG
> version — so we stay diversified.

### Step 2 · Why a fund was excluded (20 s)

**Click:** *Ethics* tab, open the red VXUS line.

> Why? Shell is one of its top holdings, and Moderate excludes fossil
> fuels. Every company is checked with open data.

### Step 3 · Harvard today (45 s)

**In the sidebar:**
1. *Private equity*: select **40% (Harvard today)**.
2. *Excise tax rate*: move to **8**.
3. *Annual payout rate*: move to **7.0**.

> Now let's get closer to Harvard's situation today: 40% in private equity,
> the 8% tax, and a 7% payout.
> Orange banner: **no strategy passes** anymore. After a crash, Balanced
> pays every scholarship in only **72%** of futures.
> And the app tells us what would work: about **6,750 dollars a year** at
> most, instead of 7,000.

### Step 4 · The liquidity problem, live (40 s)

**Click:** *Liquidity* tab.

> This is Harvard's liquidity problem. The private equity share climbs to
> about **82%** of the fund. And look at this number: after a crash, in
> **28%** of futures a scholarship is missed **while the money exists** —
> it's locked in private equity. With 20%, that would be under 2%.

**Point at the chart:** the 40% line rises far above the 20% line.

### Step 5 · The cost of the tax (20 s)

**Click:** *Endowment tax* tab.

> And the 8% tax costs this fund about **2,300 dollars** over 10 years,
> compared with zero without it.

### Step 6 · Ask the analyst (50 s)

**Click:** *AI analyst* tab. In the chat, type:

> *Bring private equity back to 20% and set the payout to 6%.*

> I'm asking the analyst in plain English. It answers, and it changes the
> settings itself.

**Wait for the reply** (about 15–30 s). The sidebar updates and the
banner turns **green: Balanced recommended**.

> Back to green. With 20% private equity and a 6% payout, Balanced pays
> every scholarship even after a crash, and no scholarship is ever missed
> because of locked money.

**Optional (if time):** click *Write committee memo*.

> And in one click, the committee gets a memo explaining the decision,
> with every number checked.

### Step 7 · Wrap-up (10 s)

> That's the Scholarship AI Analyst: choose a scenario, read the verdict,
> ask why. Thank you — happy to take questions.

### If something goes wrong

| Problem | What to do |
|---|---|
| A step takes several seconds | Normal on the first run of the day; that's why you warm it up. Say “it's running 1,000 futures on 19 years of data”. |
| The AI is slow or fails | Show the pre-generated memo; set the sliders by hand instead of the chat. |
| The chat doesn't change the settings | Set *Private equity* to 20% and the payout to 6.0 in the sidebar. |
| An error page | Stop the app and run `streamlit run app.py` again. |

*Figures were computed with the market data of 23 October 2026; they
move slightly with new data.*
