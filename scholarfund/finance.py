import numpy as np
import pandas as pd

# ScholarFund AI — investment model
# Educational prototype, not financial advice.

INITIAL_CAPITAL = 100_000
ANNUAL_PAYOUT = 5_000
INFLATION_RATE = 0.03

RESERVE_YEARS = 2

# Strategies ordered from least to most risky.
RISK_ORDER = ["Conservative", "Balanced", "Growth"]
RISK_LEVELS = set(RISK_ORDER)
ETHICAL_POLICIES = {"Standard", "Moderate", "Strict"}

# The fund = private equity (illiquid) + public markets.
# Harvard holds over 40% in private equity, which strained its liquidity;
# the model targets 20%. The 9% yearly return is an illustrative,
# deliberately conservative assumption (below the 11-13% of the last 15
# years). Capital is locked for PE_LOCK_YEARS: it cannot pay scholarships
# or refill the reserve before that.
PE_SHARE = 0.20
PE_ANNUAL_RETURN = 0.09
PE_LOCK_YEARS = 7
PE_LABEL = "PE"

# Public markets: two asset classes, each at least 30% of public markets.
# The share of bonds and bills depends on the risk profile; the reserve is
# part of it. Each class is split into zones (US first, with some
# international diversification). Each zone lists its funds in order of
# preference: if the first is ethically excluded, the next one (an ESG
# fund of the same zone) takes its place, so the money stays spread across
# zones instead of piling into one fund.
MIN_CLASS_SHARE = 0.30
BOND_SHARE = {
    "Conservative": 0.70,
    "Balanced": 0.50,
    "Growth": 0.30,
}
ASSET_CLASSES = {
    "bonds_and_bills": {
        "US Treasury bills": (0.15, ["BIL"]),
        "US bonds": (0.65, ["BND"]),
        "International bonds": (0.20, ["BNDX"]),
    },
    "stocks": {
        "US stocks": (0.65, ["VTI", "ESGV"]),
        "International stocks": (0.35, ["VXUS", "VSGX"]),
    },
}
LOW_RISK_ASSETS = {
    fund
    for _, funds in ASSET_CLASSES["bonds_and_bills"].values()
    for fund in funds
}

# The cash bucket (scholarship reserve) is held in this asset when it is
# eligible; otherwise it earns 0%.
CASH_ASSET = "BIL"

# Forced-sale avoidance: the growth bucket is not sold while it is more
# than this far below its previous peak, unless nothing else is left.
GROWTH_DRAWDOWN_LIMIT = 0.10

# Illustrative one-month shock applied per asset class in the stress test.
# Assets not listed receive the equity shock, to stay on the cautious side.
STRESS_SHOCKS = {
    "BIL": 0.00,
    "BND": -0.10,
    "BNDX": -0.10,
    "VTI": -0.40,
    "VXUS": -0.40,
    "ESGV": -0.40,
    "VSGX": -0.40,
    PE_LABEL: -0.30,
}
DEFAULT_STRESS_SHOCK = -0.40

# US endowment excise tax, tiered from 2026 by endowment per student.
# In the model it is paid on the gain realized whenever an asset that has
# risen in value is sold (to pay scholarships, refill the reserve or
# rebalance).
EXCISE_TAX_TIERS = {
    "Off": 0.0,
    "1.4% tier": 0.014,
    "4% tier": 0.04,
    "8% tier": 0.08,
}

# Long-horizon Monte Carlo settings.
HORIZON_YEARS = 10
N_SIMULATIONS = 1_000
BLOCK_SIZE = 12
MIN_SUCCESS_RATE = 0.90

SHORTFALL_TOLERANCE = 0.005


def validate_inputs(
    asset_returns, risk_tolerance, ethical_policy,
    annual_payout, inflation_rate, initial_capital
):
    if risk_tolerance not in RISK_LEVELS:
        raise ValueError(f"risk_tolerance must be one of {RISK_LEVELS}")
    if ethical_policy not in ETHICAL_POLICIES:
        raise ValueError(f"ethical_policy must be one of {ETHICAL_POLICIES}")
    if not isinstance(asset_returns, pd.DataFrame) or asset_returns.empty:
        raise ValueError("asset_returns must be a non-empty pandas DataFrame")
    if annual_payout < 0 or initial_capital <= 0:
        raise ValueError("Payout cannot be negative; capital must be positive")
    if inflation_rate <= -1:
        raise ValueError("Inflation rate must be greater than -100%")


def calculate_reserve_amount(annual_payout, inflation_rate, reserve_years):
    """
    Amount needed to cover reserve_years of inflation-indexed payouts.

    With $5,000 and 3% inflation over 2 years: 5,000 + 5,150 = $10,150.
    """
    return float(sum(
        annual_payout * (1 + inflation_rate) ** year
        for year in range(reserve_years)
    ))


def monthly_payment_due(month_index, annual_payout, inflation_rate):
    """Monthly payment, indexed on inflation once every 12 months."""
    return annual_payout * (1 + inflation_rate) ** (month_index // 12) / 12


def calculate_portfolio_returns(asset_returns, weights):
    """
    Calculate monthly returns using fixed target weights.

    Fixed weights imply the portfolio is rebalanced every month.
    """
    weights = pd.Series(weights, dtype=float)
    weights = weights[weights > 0]

    if weights.empty:
        raise ValueError("No eligible assets remain.")

    missing = set(weights.index) - set(asset_returns.columns)
    if missing:
        raise ValueError(f"Missing asset columns: {sorted(missing)}")

    weights = weights / weights.sum()
    returns = asset_returns[weights.index].dropna()

    if returns.empty:
        raise ValueError("No complete monthly return observations.")

    return returns.mul(weights, axis=1).sum(axis=1)


def class_weights(asset_class, allowed):
    """
    Weights inside one asset class, one fund per zone.

    Each zone takes its first eligible fund. Returns the weights, the
    substitutions made ({zone: (excluded fund, replacement)}) and the zones
    left without any eligible fund, whose weight goes to the other zones.
    """
    chosen, substitutions, empty = {}, {}, []
    for zone, (weight, funds) in ASSET_CLASSES[asset_class].items():
        fund = next((f for f in funds if f in allowed), None)
        if fund is None:
            empty.append(zone)
            continue
        chosen[fund] = chosen.get(fund, 0.0) + weight
        if fund != funds[0]:
            substitutions[zone] = (funds[0], fund)

    total = sum(chosen.values())
    weights = {a: w / total for a, w in chosen.items()} if total else {}
    return weights, substitutions, empty


def build_allocation(
    strategy, allowed, initial_capital, reserve_amount, pe_share, cash_asset
):
    """
    Dollar amounts for one strategy, or (None, reason) if the rules
    cannot be met with the eligible assets.

    The fund is split into private equity and public markets. Public
    markets hold BOND_SHARE[strategy] in bonds and bills (reserve
    included) and the rest in stocks, each class at least MIN_CLASS_SHARE.
    An excluded fund is replaced by the next fund of its zone; a zone with
    no eligible fund passes its weight to the other zones of its class, so
    class shares never change.
    """
    bonds, bond_subs, bond_gaps = class_weights("bonds_and_bills", allowed)
    stocks, stock_subs, stock_gaps = class_weights("stocks", allowed)
    if not bonds or not stocks:
        missing = "bonds and bills" if not bonds else "stocks"
        return None, (
            f"No eligible {missing}: public markets need at least "
            f"{MIN_CLASS_SHARE:.0%} in each of bonds/bills and stocks."
        )

    pe_amount = initial_capital * pe_share
    public = initial_capital - pe_amount
    bond_amount = max(public * BOND_SHARE[strategy], reserve_amount)
    stock_amount = public - bond_amount

    if stock_amount < public * MIN_CLASS_SHARE - 1e-6:
        return None, (
            "The scholarship reserve is too large: stocks would fall below "
            f"{MIN_CLASS_SHARE:.0%} of public markets."
        )

    low_amount = bond_amount - reserve_amount
    amounts = {asset: low_amount * w for asset, w in bonds.items()}
    for asset, w in stocks.items():
        amounts[asset] = amounts.get(asset, 0.0) + stock_amount * w
    reserve_key = cash_asset or "Cash"
    amounts[reserve_key] = amounts.get(reserve_key, 0.0) + reserve_amount
    if pe_amount > 0:
        amounts[PE_LABEL] = pe_amount

    return {
        "amounts": amounts,
        "bond_weights": bonds,
        "stock_weights": stocks,
        "substitutions": {**bond_subs, **stock_subs},
        "uncovered_zones": bond_gaps + stock_gaps,
        "reserve": reserve_amount,
        "low": low_amount,
        "growth": stock_amount,
        "pe": pe_amount,
        "public": public,
        "bond_share_of_public": bond_amount / public,
        "stock_share_of_public": stock_amount / public,
    }, None


def calculate_bucket_returns(asset_returns, allocation, cash_asset, pe_return):
    """
    Monthly returns of the four buckets: cash, lower-risk, growth and
    private equity (constant pe_return per year).
    """
    zero = pd.Series(0.0, index=asset_returns.index)
    pe_monthly = (1 + pe_return) ** (1 / 12) - 1

    return pd.DataFrame({
        "cash": (
            asset_returns[cash_asset] if cash_asset is not None else zero
        ),
        "low_risk": calculate_portfolio_returns(
            asset_returns, allocation["bond_weights"]
        ),
        "growth": calculate_portfolio_returns(
            asset_returns, allocation["stock_weights"]
        ),
        "pe": zero + pe_monthly,
    })


def _sell(value, basis, need, tax_rate, allowed=True):
    """
    Sell enough of a bucket to raise `need` after tax on realized gains.

    The gain is the share of the sale above its cost basis. Returns the
    new value and basis, the cash raised and the tax paid.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        gain_share = np.where(value > 0, 1 - basis / value, 0.0)
    gain_share = np.clip(gain_share, 0.0, 1.0)

    gross = need / (1 - tax_rate * gain_share)
    sold = np.where(allowed, np.minimum(value, gross), 0.0)
    tax = sold * tax_rate * gain_share

    with np.errstate(divide="ignore", invalid="ignore"):
        kept = np.where(value > 0, 1 - sold / value, 0.0)
    return value - sold, basis * kept, sold - tax, tax


def simulate_buckets(
    cash_returns,
    low_returns,
    growth_returns,
    pe_returns,
    allocation,
    annual_payout,
    inflation_rate,
    reserve_years=RESERVE_YEARS,
    tax_rate=0.0,
    pe_lock_years=PE_LOCK_YEARS,
    record=False,
):
    """
    Simulate scholarship payments with four buckets, for many paths at once.

    Return arrays have shape (n_paths, n_months). Each month:
    1. Every bucket earns its return.
    2. The scholarship is paid from the cash bucket. Only if cash is empty,
       the lower-risk bucket pays, then the growth bucket (counted as a
       forced sale if growth is in drawdown), then private equity once its
       lock-up is over.
    3. The cash bucket is refilled up to the next reserve_years of payouts:
       from growth if growth is not in drawdown, then from lower-risk, then
       from unlocked private equity.
    4. Once a year, lower-risk and growth are rebalanced to their target
       split, unless growth is in drawdown. Private equity is never
       rebalanced.
    Every sale of an asset that has gained value pays tax_rate on the
    realized gain (endowment excise tax), so more must be sold.
    """
    n_paths, n_months = cash_returns.shape
    reserve_months = reserve_years * 12
    lock_months = pe_lock_years * 12

    payments = np.array([
        monthly_payment_due(m, annual_payout, inflation_rate)
        for m in range(n_months + reserve_months + 1)
    ])
    # Reserve target after month m: payouts due over the following months.
    cumulative = np.concatenate([[0.0], np.cumsum(payments)])
    reserve_target = (
        cumulative[np.arange(n_months) + 1 + reserve_months]
        - cumulative[np.arange(n_months) + 1]
    )

    def start(amount):
        return np.full(n_paths, float(amount))

    cash = start(allocation["reserve"])
    low, low_basis = start(allocation["low"]), start(allocation["low"])
    growth = start(allocation["growth"])
    growth_basis = growth.copy()
    pe, pe_basis = start(allocation["pe"]), start(allocation["pe"])
    invested = allocation["low"] + allocation["growth"]
    low_share = allocation["low"] / invested if invested else 0.0

    growth_index = np.ones(n_paths)
    growth_peak = np.ones(n_paths)
    failed = np.zeros(n_paths, dtype=bool)
    forced = np.zeros(n_paths, dtype=bool)
    illiquid = np.zeros(n_paths, dtype=bool)
    tax_paid = np.zeros(n_paths)
    pe_share_max = np.zeros(n_paths)

    keys = [
        "payment_due", "cash_payment", "low_risk_payment", "growth_payment",
        "pe_payment", "payment_made", "shortfall", "forced_growth_sale",
        "tax_paid", "cash_balance", "low_risk_balance", "growth_balance",
        "pe_balance", "total_balance",
    ]
    history = (
        {key: np.zeros((n_paths, n_months)) for key in keys}
        if record else None
    )

    for m in range(n_months):
        tax_month = np.zeros(n_paths)
        pe_unlocked = m >= lock_months

        # 1. Returns.
        cash = np.maximum(0.0, cash * (1 + cash_returns[:, m]))
        low = np.maximum(0.0, low * (1 + low_returns[:, m]))
        growth = np.maximum(0.0, growth * (1 + growth_returns[:, m]))
        pe = np.maximum(0.0, pe * (1 + pe_returns[:, m]))

        growth_index = growth_index * (1 + growth_returns[:, m])
        growth_peak = np.maximum(growth_peak, growth_index)
        growth_ok = growth_index >= growth_peak * (1 - GROWTH_DRAWDOWN_LIMIT)

        # 2. Payment: cash, then lower-risk, growth, unlocked PE.
        payment_due = payments[m]
        cash_payment = np.minimum(cash, payment_due)
        cash -= cash_payment
        remaining = payment_due - cash_payment

        low, low_basis, low_payment, tax = _sell(
            low, low_basis, remaining, tax_rate
        )
        remaining -= low_payment
        tax_month += tax

        growth, growth_basis, growth_payment, tax = _sell(
            growth, growth_basis, remaining, tax_rate
        )
        remaining -= growth_payment
        tax_month += tax

        pe, pe_basis, pe_payment, tax = _sell(
            pe, pe_basis, remaining, tax_rate, allowed=pe_unlocked
        )
        remaining -= pe_payment
        tax_month += tax

        remaining = np.maximum(remaining, 0.0)
        forced_sale = (growth_payment > SHORTFALL_TOLERANCE) & ~growth_ok
        forced |= forced_sale
        short = remaining > SHORTFALL_TOLERANCE
        failed |= short
        # Money existed but was locked in private equity.
        illiquid |= short & (not pe_unlocked) & (pe > remaining)

        # 3. Refill the reserve without selling growth in drawdown.
        need = np.maximum(0.0, reserve_target[m] - cash)

        growth, growth_basis, raised, tax = _sell(
            growth, growth_basis, need, tax_rate, allowed=growth_ok
        )
        need -= raised
        cash += raised
        tax_month += tax

        low, low_basis, raised, tax = _sell(low, low_basis, need, tax_rate)
        need -= raised
        cash += raised
        tax_month += tax

        pe, pe_basis, raised, tax = _sell(
            pe, pe_basis, need, tax_rate, allowed=pe_unlocked
        )
        cash += raised
        tax_month += tax

        # 4. Annual rebalancing of lower-risk and growth.
        if m % 12 == 11:
            target_low = (low + growth) * low_share
            excess_low = np.where(growth_ok, low - target_low, 0.0)

            low, low_basis, moved, tax = _sell(
                low, low_basis, np.maximum(excess_low, 0.0), tax_rate
            )
            growth += moved
            growth_basis += moved
            tax_month += tax

            growth, growth_basis, moved, tax = _sell(
                growth, growth_basis, np.maximum(-excess_low, 0.0), tax_rate
            )
            low += moved
            low_basis += moved
            tax_month += tax

        tax_paid += tax_month
        total = cash + low + growth + pe
        with np.errstate(divide="ignore", invalid="ignore"):
            pe_share_max = np.maximum(
                pe_share_max, np.where(total > 0, pe / total, 0.0)
            )

        if record:
            history["payment_due"][:, m] = payment_due
            history["cash_payment"][:, m] = cash_payment
            history["low_risk_payment"][:, m] = low_payment
            history["growth_payment"][:, m] = growth_payment
            history["pe_payment"][:, m] = pe_payment
            history["payment_made"][:, m] = payment_due - remaining
            history["shortfall"][:, m] = remaining
            history["forced_growth_sale"][:, m] = forced_sale
            history["tax_paid"][:, m] = tax_month
            history["cash_balance"][:, m] = cash
            history["low_risk_balance"][:, m] = low
            history["growth_balance"][:, m] = growth
            history["pe_balance"][:, m] = pe
            history["total_balance"][:, m] = total

    return {
        "ending_balance": cash + low + growth + pe,
        "ending_cash": cash,
        "funding_failure": failed,
        "forced_growth_sale": forced,
        "illiquidity_failure": illiquid,
        "tax_paid": tax_paid,
        "pe_share_max": pe_share_max,
        "history": history,
    }


def simulate_payouts(
    bucket_returns,
    allocation,
    annual_payout=ANNUAL_PAYOUT,
    inflation_rate=INFLATION_RATE,
    reserve_years=RESERVE_YEARS,
    tax_rate=0.0,
    pe_lock_years=PE_LOCK_YEARS,
):
    """
    Simulate scholarship payments over the historical bucket returns.

    bucket_returns: DataFrame with columns cash, low_risk, growth and pe.
    """
    def row(column):
        return bucket_returns[column].to_numpy()[None, :]

    result = simulate_buckets(
        row("cash"),
        row("low_risk"),
        row("growth"),
        row("pe"),
        allocation,
        annual_payout,
        inflation_rate,
        reserve_years=reserve_years,
        tax_rate=tax_rate,
        pe_lock_years=pe_lock_years,
        record=True,
    )
    history = pd.DataFrame(
        {key: values[0] for key, values in result["history"].items()},
        index=bucket_returns.index,
    )
    history["forced_growth_sale"] = history["forced_growth_sale"].astype(bool)

    failures = history.index[history["shortfall"] > SHORTFALL_TOLERANCE]

    return {
        "history": history,
        "ending_balance": float(result["ending_balance"][0]),
        "ending_cash": float(result["ending_cash"][0]),
        "initial_reserve": float(allocation["reserve"]),
        "total_required": float(history["payment_due"].sum()),
        "total_paid": float(history["payment_made"].sum()),
        "total_shortfall": float(history["shortfall"].sum()),
        "total_tax_paid": float(history["tax_paid"].sum()),
        "short_payments": len(failures),
        "funding_failure": len(failures) > 0,
        "illiquidity_failure": bool(result["illiquidity_failure"][0]),
        "first_failure_month": (
            str(pd.Timestamp(failures[0]).date()) if len(failures) else None
        ),
        "forced_growth_sales": int(history["forced_growth_sale"].sum()),
    }


def bootstrap_path_indices(
    n_observations,
    n_months,
    n_simulations=N_SIMULATIONS,
    block_size=BLOCK_SIZE,
    seed=None,
):
    """
    Draw row indices for a block bootstrap of historical months.

    Consecutive blocks of months are resampled with replacement, which keeps
    part of the short-term dependence between months. The same indices are
    reused for every strategy so the comparison is fair.
    """
    rng = np.random.default_rng(seed)
    block_size = max(1, min(block_size, n_observations))
    n_blocks = int(np.ceil(n_months / block_size))

    starts = rng.integers(
        0, n_observations - block_size + 1, size=(n_simulations, n_blocks)
    )
    indices = starts[:, :, None] + np.arange(block_size)
    return indices.reshape(n_simulations, -1)[:, :n_months]


def portfolio_stress_shock(weights):
    """Portfolio loss implied by the per-asset stress shocks."""
    return float(sum(
        weight * STRESS_SHOCKS.get(asset, DEFAULT_STRESS_SHOCK)
        for asset, weight in weights.items()
    ))


def calculate_metrics(
    asset_returns,
    allocation,
    cash_asset,
    path_indices,
    annual_payout,
    inflation_rate,
    reserve_years,
    tax_rate,
    pe_return,
    pe_lock_years,
):
    """Calculate historical, long-horizon and stress metrics."""
    buckets = calculate_bucket_returns(
        asset_returns, allocation, cash_asset, pe_return
    )
    amounts = allocation["amounts"]
    initial_capital = sum(amounts.values())
    weights = {asset: v / initial_capital for asset, v in amounts.items()}

    # Return and risk of the public-market part, from market data. Private
    # equity has an assumed, constant return, so it is reported apart.
    public_weights = {
        asset: v for asset, v in amounts.items()
        if asset in asset_returns.columns
    }
    r = calculate_portfolio_returns(asset_returns, public_weights)

    annualized_return = (
        float(np.prod(1 + r) ** (12 / len(r)) - 1)
        if len(r) > 0 else 0.0
    )
    volatility = (
        float(r.std(ddof=1) * np.sqrt(12))
        if len(r) > 1 else 0.0
    )

    wealth = (1 + r).cumprod()
    max_drawdown = (
        float((wealth / wealth.cummax() - 1).min())
        if len(wealth) else 0.0
    )

    options = {
        "reserve_years": reserve_years,
        "tax_rate": tax_rate,
        "pe_lock_years": pe_lock_years,
    }
    simulation = simulate_payouts(
        buckets, allocation, annual_payout, inflation_rate, **options
    )

    # Long-horizon Monte Carlo on resampled historical months.
    paths = {
        column: buckets[column].to_numpy()[path_indices]
        for column in buckets.columns
    }

    def run_paths(paths):
        return simulate_buckets(
            paths["cash"],
            paths["low_risk"],
            paths["growth"],
            paths["pe"],
            allocation,
            annual_payout,
            inflation_rate,
            **options,
        )

    mc = run_paths(paths)

    # Same paths, with an immediate per-asset shock in the first month.
    shocks = {
        "cash": (
            STRESS_SHOCKS.get(cash_asset, DEFAULT_STRESS_SHOCK)
            if cash_asset is not None else 0.0
        ),
        "low_risk": portfolio_stress_shock(allocation["bond_weights"]),
        "growth": portfolio_stress_shock(allocation["stock_weights"]),
        "pe": STRESS_SHOCKS[PE_LABEL],
    }
    stress_paths = {column: path.copy() for column, path in paths.items()}
    for column, shock in shocks.items():
        stress_paths[column][:, 0] = shock
    stress = run_paths(stress_paths)

    history = simulation["history"]
    deflator = (1 + inflation_rate) ** (path_indices.shape[1] / 12)
    pe_share = allocation["pe"] / initial_capital

    return {
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "maximum_drawdown": max_drawdown,
        "expected_total_return": (
            (1 - pe_share) * annualized_return + pe_share * pe_return
        ),
        "ending_balance": simulation["ending_balance"],
        "ending_cash": simulation["ending_cash"],
        "initial_reserve": simulation["initial_reserve"],
        "total_paid": simulation["total_paid"],
        "total_shortfall": simulation["total_shortfall"],
        "total_tax_paid": simulation["total_tax_paid"],
        "short_payments": simulation["short_payments"],
        "funding_failure": simulation["funding_failure"],
        "first_failure_month": simulation["first_failure_month"],
        "forced_growth_sales": simulation["forced_growth_sales"],
        "balance_history": history["total_balance"],
        "reserve_history": history["cash_balance"],
        "pe_history": history["pe_balance"],
        "mc_success_rate": float(1 - mc["funding_failure"].mean()),
        "mc_forced_sale_rate": float(mc["forced_growth_sale"].mean()),
        "mc_illiquidity_failure_rate": float(
            mc["illiquidity_failure"].mean()
        ),
        "mc_tax_paid_p50": float(np.percentile(mc["tax_paid"], 50)),
        "mc_pe_share_max_p50": float(np.percentile(mc["pe_share_max"], 50)),
        "mc_ending_balance_p5": float(np.percentile(mc["ending_balance"], 5)),
        "mc_ending_balance_p50": float(np.percentile(mc["ending_balance"], 50)),
        "mc_ending_balance_p95": float(np.percentile(mc["ending_balance"], 95)),
        "stress_shock": portfolio_stress_shock(weights),
        "stress_success_rate": float(1 - stress["funding_failure"].mean()),
        "stress_forced_sale_rate": float(stress["forced_growth_sale"].mean()),
        "stress_illiquidity_failure_rate": float(
            stress["illiquidity_failure"].mean()
        ),
        "stress_ending_balance_p50": float(
            np.percentile(stress["ending_balance"], 50)
        ),
        # Real value: ending balance in today's dollars, compared with the
        # initial capital.
        "mc_real_value_preserved_rate": float(
            (mc["ending_balance"] / deflator >= initial_capital).mean()
        ),
        "mc_real_ending_balance_p50": float(
            np.percentile(mc["ending_balance"], 50) / deflator
        ),
    }


def failed_funding_checks(result, min_success_rate):
    """Human-readable list of the funding checks a strategy fails."""
    failed = []
    if result["funding_failure"]:
        failed.append(
            "missed scholarship payments over the historical period "
            f"(first in {result['first_failure_month']})"
        )
    if result["mc_success_rate"] < min_success_rate:
        failed.append(
            f"long-horizon success rate {result['mc_success_rate']:.1%} "
            f"below {min_success_rate:.0%}"
        )
    if result["stress_success_rate"] < min_success_rate:
        failed.append(
            f"stress success rate {result['stress_success_rate']:.1%} "
            f"below {min_success_rate:.0%}"
        )
    return failed


def same_weights(a, b, tolerance=1e-9):
    """True if two allocations hold the same assets with the same weights."""
    return a.keys() == b.keys() and all(
        abs(a[asset] - b[asset]) <= tolerance for asset in a
    )


def estimate_sustainable_payout(
    asset_returns,
    strategy,
    annual_payout,
    tolerance=50.0,
    **options,
):
    """
    Highest annual payout (to within `tolerance`) at which `strategy`
    passes every funding check, searched by bisection below
    annual_payout. Returns None if the strategy is unavailable, and 0.0
    if even a near-zero payout fails.

    options are passed to recommend_portfolio (inflation, capital,
    ethical policy, metadata, ...), so the test conditions are the same.
    """
    def passes(payout):
        result = recommend_portfolio(
            asset_returns,
            risk_tolerance=strategy,
            annual_payout=payout,
            **options,
        )["portfolios"][strategy]
        if not result["available"]:
            return None
        return not result["failed_checks"]

    low, high = 0.0, float(annual_payout)
    if passes(tolerance) is None:
        return None
    if not passes(tolerance):
        return 0.0

    low = tolerance
    while high - low > tolerance:
        middle = (low + high) / 2
        if passes(middle):
            low = middle
        else:
            high = middle
    return low


def recommend_portfolio(
    asset_returns,
    risk_tolerance="Balanced",
    ethical_policy="Standard",
    annual_payout=ANNUAL_PAYOUT,
    inflation_rate=INFLATION_RATE,
    initial_capital=INITIAL_CAPITAL,
    asset_metadata=None,
    reserve_years=RESERVE_YEARS,
    horizon_years=HORIZON_YEARS,
    n_simulations=N_SIMULATIONS,
    min_success_rate=MIN_SUCCESS_RATE,
    excise_tax_rate=0.0,
    pe_share=PE_SHARE,
    pe_annual_return=PE_ANNUAL_RETURN,
    pe_lock_years=PE_LOCK_YEARS,
    seed=42,
):
    """
    Compare portfolio strategies for a scholarship fund.

    The fund holds pe_share in illiquid private equity and the rest in
    public markets, split into four buckets:
    - cash: reserve_years of inflation-indexed payouts, held in CASH_ASSET;
    - lower-risk: the other bonds and bills;
    - growth: stocks;
    - private equity: locked for pe_lock_years.
    Public markets hold BOND_SHARE[strategy] in bonds and bills (reserve
    included) and the rest in stocks, each at least MIN_CLASS_SHARE.

    Scholarships are paid from the cash bucket, which is refilled without
    selling growth while it is in drawdown (see simulate_buckets). Selling
    an asset that has gained value pays excise_tax_rate on the gain.

    Only strategies no riskier than the client's risk tolerance are
    considered. Ethically excluded assets are replaced by the other assets
    of their class; a strategy whose class is left empty is unavailable.

    To be eligible for recommendation, a strategy must:
    - pay every scholarship over the historical period;
    - pay every scholarship over horizon_years in at least min_success_rate
      of the Monte Carlo paths;
    - do the same when a per-asset shock hits in the first month.

    asset_returns:
        DataFrame of monthly decimal returns.
    asset_metadata:
        Verified eligibility metadata for Moderate/Strict ethical policies.
    reserve_years:
        Number of years of inflation-indexed scholarship payouts to reserve.
    excise_tax_rate:
        Tax on realized gains when assets are sold (0.08 = 8% tier).
    pe_share, pe_annual_return, pe_lock_years:
        Private equity share of the fund, assumed yearly return and lock-up.
    """
    validate_inputs(
        asset_returns,
        risk_tolerance,
        ethical_policy,
        annual_payout,
        inflation_rate,
        initial_capital,
    )

    if reserve_years < 1:
        raise ValueError("reserve_years must be at least 1.")
    if horizon_years < 1 or n_simulations < 1:
        raise ValueError("horizon_years and n_simulations must be positive.")
    if not 0 < min_success_rate <= 1:
        raise ValueError("min_success_rate must be between 0 and 1.")
    if not 0 <= excise_tax_rate < 1:
        raise ValueError("excise_tax_rate must be between 0 and 1.")
    if not 0 <= pe_share < 1:
        raise ValueError("pe_share must be between 0 and 1.")

    if ethical_policy != "Standard" and asset_metadata is None:
        raise ValueError(
            "Moderate/Strict policies require verified asset_metadata."
        )

    # Use only months where every asset has a return, so all strategies
    # are simulated on the same dates and the same resampled paths.
    asset_returns = asset_returns.dropna(how="any")
    if asset_returns.empty:
        raise ValueError("No complete monthly return observations.")

    # 1. The reserve comes out of the public-market bonds and bills.
    reserve_amount = calculate_reserve_amount(
        annual_payout, inflation_rate, reserve_years
    )
    public_capital = initial_capital * (1 - pe_share)
    if reserve_amount >= public_capital:
        raise ValueError(
            "The scholarship reserve exceeds the public-market capital."
        )

    # 2. Apply ethical eligibility rules.
    if ethical_policy == "Standard":
        allowed = set(asset_returns.columns)
        excluded = []
    else:
        allowed = set()
        excluded = []

        for asset in asset_returns.columns:
            status = asset_metadata.get(asset, {}).get(ethical_policy)
            if status is True:
                allowed.add(asset)
            else:
                excluded.append(asset)

    cash_asset = CASH_ASSET if CASH_ASSET in allowed else None

    client_rank = RISK_ORDER.index(risk_tolerance)
    path_indices = bootstrap_path_indices(
        len(asset_returns),
        horizon_years * 12,
        n_simulations=n_simulations,
        seed=seed,
    )

    results = {}

    # 3. Build and simulate each strategy.
    for name in RISK_ORDER:
        if RISK_ORDER.index(name) > client_rank:
            results[name] = {
                "available": False,
                "reason": "Riskier than the client's risk tolerance.",
            }
            continue

        allocation, reason = build_allocation(
            name, allowed, initial_capital, reserve_amount, pe_share,
            cash_asset,
        )
        if allocation is None:
            results[name] = {"available": False, "reason": reason}
            continue

        metrics = calculate_metrics(
            asset_returns,
            allocation,
            cash_asset,
            path_indices,
            annual_payout,
            inflation_rate,
            reserve_years,
            excise_tax_rate,
            pe_annual_return,
            pe_lock_years,
        )

        amounts = allocation["amounts"]
        results[name] = {
            "available": True,
            "amounts": amounts,
            "weights": {
                asset: value / initial_capital
                for asset, value in amounts.items()
            },
            "bond_share_of_public": allocation["bond_share_of_public"],
            "stock_share_of_public": allocation["stock_share_of_public"],
            "fund_substitutions": {
                zone: {"excluded": old, "replaced_by": new}
                for zone, (old, new) in allocation["substitutions"].items()
            },
            "uncovered_zones": allocation["uncovered_zones"],
            "reserve_amount": reserve_amount,
            **metrics,
        }

    # 4. Record which funding checks each strategy fails, and flag
    # strategies that ended up with the same allocation after filtering.
    for name, result in results.items():
        if not result["available"]:
            continue
        result["failed_checks"] = failed_funding_checks(
            result, min_success_rate
        )
        for other in RISK_ORDER[:RISK_ORDER.index(name)]:
            other_result = results.get(other, {})
            if other_result.get("available") and same_weights(
                result["weights"], other_result["weights"]
            ):
                result["same_allocation_as"] = other
                break

    candidates = {
        name: result
        for name, result in results.items()
        if result["available"] and not result["failed_checks"]
    }

    # 5. Recommend the strategy matching the client's risk tolerance if it
    # passes every check; otherwise fall back to the next less risky one.
    # Never force a recommendation if none qualify.
    preference = RISK_ORDER[:client_rank + 1][::-1]
    recommended_name = next(
        (name for name in preference if name in candidates), None
    )

    if recommended_name is None:
        recommendation_status = "no_strategy_passed_funding_tests"
        recommendation_reason = (
            "No strategy within the client's risk tolerance passed every "
            "funding test."
        )
    elif recommended_name == risk_tolerance:
        recommendation_status = "eligible_strategy_found"
        recommendation_reason = (
            f"{recommended_name} matches the client's risk tolerance and "
            "passed every funding test."
        )
    else:
        recommendation_status = "eligible_strategy_found"
        skipped = []
        for name in preference[:preference.index(recommended_name)]:
            skipped_result = results[name]
            why = skipped_result.get("reason") or "; ".join(
                skipped_result["failed_checks"]
            )
            skipped.append(f"{name} ({why})")
        recommendation_reason = (
            f"{recommended_name} is the most growth-oriented strategy "
            "within the client's risk tolerance that passed every funding "
            "test. Not retained: " + "; ".join(skipped) + "."
        )

    return {
        "recommendation": recommended_name,
        "recommendation_status": recommendation_status,
        "recommendation_reason": recommendation_reason,
        "client_inputs": {
            "risk_tolerance": risk_tolerance,
            "ethical_policy": ethical_policy,
            "annual_payout": annual_payout,
            "inflation_rate": inflation_rate,
            "initial_capital": initial_capital,
            "reserve_years": reserve_years,
            "reserve_amount": reserve_amount,
            "reserve_asset": cash_asset,
            "public_capital": public_capital,
            "pe_share": pe_share,
            "pe_annual_return": pe_annual_return,
            "pe_lock_years": pe_lock_years,
            "horizon_years": horizon_years,
            "n_simulations": n_simulations,
            "min_success_rate": min_success_rate,
            "excise_tax_rate": excise_tax_rate,
        },
        "portfolios": results,
        "eligible_strategies": list(candidates.keys()),
        "excluded_or_unverified_assets": excluded,
        "disclaimer": (
            "Educational prototype only. Passing historical, resampled and "
            "stress scenarios does not guarantee future scholarship payments "
            "or preservation of capital. Private equity returns are an "
            "illustrative assumption. Investments can lose value. "
            "Not financial advice."
        ),
    }
