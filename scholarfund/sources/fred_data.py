"""
ScholarFund AI
Macroeconomic data loader using FRED (Federal Reserve Bank of St. Louis).

Provides the inflation assumption for scholarship indexation and the
current short-term Treasury rate earned by the cash reserve.
"""

import pandas as pd
import requests

from ..config import get_api_key

BASE_URL = "https://api.stlouisfed.org/fred"
TIMEOUT_SECONDS = 30

# Consumer Price Index for All Urban Consumers, monthly, 1982-84 = 100.
CPI_SERIES = "CPIAUCSL"
# 3-month Treasury bill secondary market rate, monthly, in percent.
TBILL_SERIES = "TB3MS"


class FredError(RuntimeError):
    pass


def get_series(series_id, start=None):
    """
    Download one FRED series as a float pandas Series indexed by date.

    Missing observations (reported by FRED as ".") are dropped.
    """
    params = {
        "series_id": series_id,
        "api_key": get_api_key("FRED_API_KEY"),
        "file_type": "json",
    }
    if start is not None:
        params["observation_start"] = str(pd.Timestamp(start).date())

    response = requests.get(
        f"{BASE_URL}/series/observations",
        params=params,
        timeout=TIMEOUT_SECONDS,
    )
    payload = response.json()

    if response.status_code != 200:
        raise FredError(
            f"FRED request for {series_id} failed: "
            f"{payload.get('error_message', response.status_code)}"
        )

    observations = pd.DataFrame(payload.get("observations", []))
    if observations.empty:
        raise FredError(f"FRED returned no observations for {series_id}.")

    series = pd.Series(
        pd.to_numeric(observations["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(observations["date"]),
        name=series_id,
    )
    return series.dropna()


def get_inflation_assumption(years=10):
    """
    Annualized CPI inflation over the last `years` years, as a decimal.

    A long window smooths out short inflation spikes, which suits an
    assumption applied to scholarships over many years.
    """
    start = pd.Timestamp.today() - pd.DateOffset(years=years + 1)
    cpi = get_series(CPI_SERIES, start=start)

    months = years * 12
    if len(cpi) <= months:
        raise FredError(f"Not enough CPI history for {years} years.")

    return float((cpi.iloc[-1] / cpi.iloc[-1 - months]) ** (1 / years) - 1)


def get_latest_inflation():
    """Year-over-year CPI inflation for the latest available month."""
    start = pd.Timestamp.today() - pd.DateOffset(years=2)
    cpi = get_series(CPI_SERIES, start=start)
    return float(cpi.iloc[-1] / cpi.iloc[-13] - 1), cpi.index[-1]


def get_tbill_rate():
    """Latest 3-month Treasury bill rate, as an annual decimal."""
    start = pd.Timestamp.today() - pd.DateOffset(years=1)
    rates = get_series(TBILL_SERIES, start=start)
    return float(rates.iloc[-1] / 100), rates.index[-1]


if __name__ == "__main__":
    long_run = get_inflation_assumption(years=10)
    latest, latest_date = get_latest_inflation()
    tbill, tbill_date = get_tbill_rate()

    print(f"10-year annualized CPI inflation: {long_run:.2%}")
    print(f"Latest year-over-year CPI ({latest_date.date()}): {latest:.2%}")
    print(f"3-month T-bill rate ({tbill_date.date()}): {tbill:.2%}")
