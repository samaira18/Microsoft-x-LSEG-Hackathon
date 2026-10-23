import numpy as np
import pandas as pd

from scholarfund.sources.market_data import splice_proxies


def test_proxy_fills_only_months_before_launch():
    dates = pd.date_range("2010-01-31", periods=5, freq="ME")
    returns = pd.DataFrame({
        "VXUS": [np.nan, np.nan, 0.03, np.nan, 0.05],
        "VEU": [0.01, 0.02, 0.031, 0.04, 0.051],
    }, index=dates)

    spliced, used = splice_proxies(returns, {"VXUS": "VEU"})

    assert list(spliced["VXUS"].iloc[:3]) == [0.01, 0.02, 0.03]
    # A gap after launch is not filled with proxy data.
    assert np.isnan(spliced["VXUS"].iloc[3])
    assert used == {"VXUS": {"proxy": "VEU", "until": "2010-02-28"}}


def test_missing_proxy_is_ignored():
    dates = pd.date_range("2010-01-31", periods=2, freq="ME")
    returns = pd.DataFrame({"VXUS": [np.nan, 0.01]}, index=dates)
    spliced, used = splice_proxies(returns, {"VXUS": "VEU"})
    assert used == {}
    assert spliced.equals(returns)
