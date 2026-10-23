"""
ScholarFund AI
Market data loader using Yahoo Finance.

Downloads ETF price history and converts it into
monthly decimal returns for finance.py.
"""

import pandas as pd
import yfinance as yf


TICKERS = ["BIL", "BND", "BNDX", "VTI", "VXUS", "ESGV", "VSGX"]

# Before an ETF existed, its returns are taken from a close substitute.
# VEU (FTSE All-World ex-US, since 2007) tracks VXUS (since 2011) with a
# 0.998 monthly correlation. BNDX (international bonds hedged to USD,
# since 2013) is closest to BND (US bonds): 0.86 correlation and similar
# volatility, better than unhedged international bond funds. The ESG funds
# ESGV and VSGX (since 2018) follow VTI and VXUS with a 0.994 correlation.
# Order matters: VXUS is filled before it stands in for VSGX.
PROXIES = {"VXUS": "VEU", "BNDX": "BND", "ESGV": "VTI", "VSGX": "VXUS"}


def splice_proxies(monthly_returns, proxies=PROXIES):
    """
    Fill each asset's returns before its first observation with its proxy.

    Only the months before the asset existed are filled; later gaps are
    left as they are. Returns the spliced returns and, per asset, the
    proxy used and the last month it was used for.
    """
    monthly_returns = monthly_returns.copy()
    used = {}

    for asset, proxy in proxies.items():
        if asset not in monthly_returns or proxy not in monthly_returns:
            continue

        first = monthly_returns[asset].first_valid_index()
        if first is None:
            continue

        before = (
            (monthly_returns.index < first)
            & monthly_returns[proxy].notna()
        )
        if before.any():
            monthly_returns.loc[before, asset] = (
                monthly_returns.loc[before, proxy]
            )
            used[asset] = {
                "proxy": proxy,
                "until": str(monthly_returns.index[before][-1].date()),
            }

    return monthly_returns, used


def get_market_data(period="max"):
    """
    Download adjusted historical prices for the ETFs.

    Returns:
        prices: monthly adjusted closing prices
        monthly_returns: monthly decimal returns, with proxy returns before
            an ETF's launch (details in monthly_returns.attrs["proxies"])
    """
    proxy_tickers = sorted(set(PROXIES.values()) - set(TICKERS))

    downloaded = yf.download(
        tickers=TICKERS + proxy_tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )

    if downloaded.empty:
        raise ValueError(
            "Yahoo Finance returned no data. "
            "Check your internet connection and try again."
        )

    # Extract the adjusted Close prices.
    if isinstance(downloaded.columns, pd.MultiIndex):
        if "Close" not in downloaded.columns.get_level_values(0):
            raise ValueError("Could not find closing prices.")

        prices = downloaded["Close"].copy()
    else:
        # Fallback if Yahoo returns a single-level column layout.
        if "Close" not in downloaded.columns:
            raise ValueError("Could not find closing prices.")

        prices = downloaded[["Close"]].copy()
        prices.columns = [TICKERS[0]]

    # Keep the expected assets and their proxies.
    available_tickers = [
        ticker for ticker in TICKERS + proxy_tickers
        if ticker in prices.columns
    ]

    prices = prices[available_tickers].sort_index()
    prices = prices.apply(pd.to_numeric, errors="coerce")

    # Convert daily prices into month-end prices.
    monthly_prices = prices.resample("ME").last()

    # Drop the current month: it is not finished, so its "month-end"
    # price is just the latest available close.
    current_month = pd.Timestamp.today().to_period("M")
    monthly_prices = monthly_prices[
        monthly_prices.index.to_period("M") < current_month
    ]

    # Percentage change expressed as a decimal:
    # 0.02 means +2%, and -0.03 means -3%.
    monthly_returns = monthly_prices.pct_change(fill_method=None)

    monthly_returns, proxies_used = splice_proxies(monthly_returns)
    monthly_returns = monthly_returns.drop(
        columns=proxy_tickers, errors="ignore"
    )
    monthly_prices = monthly_prices.drop(
        columns=proxy_tickers, errors="ignore"
    )

    # Drop incomplete rows so the finance engine receives
    # aligned returns for all available assets.
    monthly_returns = monthly_returns.dropna(how="any")

    if monthly_returns.empty:
        raise ValueError(
            "Not enough complete monthly price data to calculate returns."
        )

    monthly_returns.attrs["proxies"] = proxies_used
    return monthly_prices, monthly_returns


if __name__ == "__main__":
    prices, returns = get_market_data()

    print("\nMONTHLY ADJUSTED PRICES — LAST 5 ROWS")
    print(prices.tail())

    print("\nMONTHLY RETURNS — LAST 5 ROWS")
    print(returns.tail())

    print("\nDATA SUMMARY")
    print(f"Assets: {list(returns.columns)}")
    print(f"Monthly observations: {len(returns)}")
    print(f"First return date: {returns.index.min().date()}")
    print(f"Last return date: {returns.index.max().date()}")
    for asset, proxy in returns.attrs["proxies"].items():
        print(f"{asset}: {proxy['proxy']} returns used until {proxy['until']}")
