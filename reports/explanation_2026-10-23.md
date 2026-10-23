## 1. Recommendation

**No strategy is recommended.** None within the committee’s Growth risk tolerance passed every funding test for a $5,000 annual payout, indexed to inflation.

The model’s sustainable starting annual payouts—rounded to the nearest $50—were:
- **Conservative: $3,900**
- **Balanced: $4,050**
- **Growth: $4,000**

These lower payout levels passed the tested scenarios; they are not promises of future funding.

## 2. Why

The model considers only strategies no riskier than the stated tolerance. With **Growth** tolerance, all three strategies were eligible. It would select Growth if it passed, otherwise the next less risky strategy that passed.

Each strategy also met its minimum lower-risk allocation. The model treats **BIL and BND** as lower-risk assets:

| Strategy | Lower-risk share | Required minimum |
|---|---:|---:|
| Conservative | 95% | 80% |
| Balanced | 77.78% | 60% |
| Growth | 50% | 40% |

From the **$100,000** initial capital, the model set aside **$10,170.38 in BIL**, leaving **$89,829.62** investable. This reserve represents two years of inflation-indexed payouts and is refilled monthly. Payouts rise using the model’s **3.41% annual inflation assumption**.

To pass, a strategy had to:
- Pay every scholarship in the historical test.
- Fund payments in at least **90% of 1,000 simulated 20-year paths**.
- Meet the same **90% threshold** after a first-month market shock.

## 3. Risks and stress test

| Strategy | Historical funding test | Normal simulation success | Stress success |
|---|---|---:|---:|
| Conservative | Failed; first missed payment September 30, 2024 | 0.3% — failed | 0.0% — failed |
| Balanced | Passed | 61.8% — failed | 8.7% — failed |
| Growth | Passed | 90.6% — passed | 51.4% — failed |

**Growth came closest**, but its stress success rate of **51.4%** remained well below the required **90%**.

The stress test applies first-month shocks of **0% to BIL, −10% to BND, and −40% to VTI and VXUS**. The resulting strategy shocks were **−4.5% for Conservative, −12.78% for Balanced, and −23.13% for Growth**.

The model also tries to avoid selling equities while they are **more than 10% below their peak** to pay scholarships or refill the reserve. It sells them only if nothing else remains, recording a forced sale. There were **no forced growth-asset sales in the historical tests**, but simulated forced-sale rates were:

| Strategy | Normal paths | Stressed paths |
|---|---:|---:|
| Conservative | 3.5% | 3.8% |
| Balanced | 6.3% | 11.8% |
| Growth | 7.0% | 19.6% |

Historical maximum drawdowns—the largest declines from a peak—were **4.75%, 11.22%, and 27.25%**, respectively. The reserve and sale-avoidance rule therefore reduced neither funding risk nor market losses to zero.

## 4. Ethical screening

The **Moderate** policy excluded **VXUS** because its screened top holdings included **Shell plc**, classified as **Energy sector (Oil & Gas Integrated)**. Shell represented **0.62%** of the fund. Only **13.54% of VXUS** was screened, so this is not a complete assessment of its holdings.

**VTI remained eligible:** no excluded activity was identified among the top holdings screened, covering **34.67%** of the fund. Two Alphabet Inc. holdings, weighted **2.76% and 2.18%**, had a **“No”** human-rights commitment entry for 2025, but no excluded activity was recorded. VXUS also had a **“No”** entry for HSBC Holdings plc, weighted **0.76%**; its stated exclusion was driven by Shell’s activity, not HSBC’s entry.

**BIL and BND remained eligible but were not screened at company level**, because company-level holdings were not available for free. Their reported U.S. government shares were **99.8% and 52.18%**, respectively. Eligibility should not be read as comprehensive ethical clearance.

## 5. What would change the result

Reducing the starting annual payout to the modeled sustainable levels would allow strategies to pass the tested funding scenarios:

| Strategy | Tested sustainable payout | Reduction from $5,000 |
|---|---:|---:|
| Conservative | $3,900 | $1,100 |
| Balanced | $4,050 | $950 |
| Growth | $4,000 | $1,000 |

Under the stated selection rule, Growth is considered first at Growth tolerance. The JSON does not establish what other changes would be sufficient to pass.

## 6. Limitations

- **Historical coverage:** 232 monthly observations, from June 2007 through September 2026, using Yahoo Finance adjusted daily closes sampled at month-end.
- **Proxy data:** VXUS uses VEU as a proxy through January 2011.
- **Simulation horizon:** Results cover 1,000 simulated paths over 20 years; they do not establish outcomes beyond that horizon.
- **Inflation assumption:** The 3.41% rate comes from annualized CPI over 10 years, rather than a forecast of future inflation.
- **Partial ethical coverage:** Only 34.67% of VTI and 13.54% of VXUS were screened; BIL and BND had no company-level screening.
- **Analysis date:** October 23, 2026.

Educational prototype only. Passing historical, resampled and stress scenarios does not guarantee future scholarship payments or preservation of capital. Investments can lose value. Not financial advice.

---

_Numbers not found in the data: $1,100, $950_
