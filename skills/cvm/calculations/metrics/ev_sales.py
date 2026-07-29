"""metrics/ev_sales.py -- EV/Sales (Enterprise Value to Revenue) metric.

EV/Sales = Enterprise Value / Revenue

Where:
  EV (Enterprise Value) = market_cap + debt - cash
    - market_cap = price × shares
    - debt = total debt (BPP 2.01.04 + 2.02.01)
    - cash = cash and equivalents (BPA 1.01.01)
  Revenue = TTM Receita Líquida (DRE 3.01)

This is a VALUATION ratio, but unlike P/L or P/VPA it does NOT produce a
per-share intermediate value -- the ratio is the final output (EV divided by
a fundamental flow). It is therefore registered as a Type 2 fundamental
ratio (per_share_*=None) following the same pattern as ev_ebitda's ratio
half but without the per-share sibling.

EV/Sales is useful for valuing companies with negative or volatile earnings,
where P/L is meaningless. It is also more stable than P/L because revenue
is less volatile than earnings.

Engines composed: price + shares + debt + cash + revenue (5 engines)

Interpretation:
  - EV/Sales < 1.0:  cheap (low price relative to revenue)
  - EV/Sales 1.0-3.0: fair (typical for mature companies)
  - EV/Sales > 5.0: expensive (high growth expectations priced in)
  - EV/Sales = None when revenue <= 0 or EV <= 0 (ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.ev_sales import ev_sales_at, ev_sales_history
    r = ev_sales_at("PETR4", "2024-06-30")    # -> 1.8 (EV/Sales ratio)
    h = ev_sales_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations.engines.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.revenue import revenue_at, revenue_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Ratio: EV/Sales = (price × shares + debt - cash) / Revenue ---------------

def ev_sales_at(company: str, date: str) -> float | None:
    """Compute EV/Sales at a specific date.

    EV/Sales = (price × shares + debt - cash) / Revenue

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EV/Sales ratio as float, or None if any component is missing,
        revenue <= 0, or EV <= 0 (negative enterprise value -- ratio
        meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    debt = debt_at(company, date)
    if debt is None:
        return None

    cash = cash_at(company, date)
    if cash is None:
        return None

    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None  # Negative/zero revenue -> EV/Sales meaningless

    market_cap = price * shares
    ev = market_cap + debt - cash
    if ev <= 0:
        return None  # Negative enterprise value -> ratio meaningless

    return ev / revenue


# -- History: daily series with EV/Sales --------------------------------------

def ev_sales_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EV/Sales time series for a date range.

    Step-function optimization:
    - price:        daily
    - shares:       annual (step)
    - debt:         quarterly (step)
    - cash:         quarterly (step)
    - revenue:      quarterly (step, TTM)

    For each daily price, find the most recent shares, debt, cash, revenue,
    then compute EV = price × shares + debt - cash, EV/Sales = EV / revenue.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ev_sales", "ev", "debt", "cash",
                 "revenue", "shares"} sorted oldest-first.
        Entries with None (missing data, negative EV/revenue) are included
        with ev_sales=None so charts show gaps.
    """
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    shares_periods_list = shares_periods(company)
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    revenue_periods_list = revenue_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        shares = None
        for sp in reversed(shares_periods_list):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break

        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break

        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break

        ev = None
        ev_sales = None
        if (price is not None and price > 0
            and shares is not None and shares > 0
            and debt is not None
            and cash is not None
            and ttm_rev is not None and ttm_rev > 0):
            ev = price * shares + debt - cash
            if ev > 0:
                ev_sales = ev / ttm_rev

        result.append({
            "date": date,
            "price": price,
            "ev_sales": ev_sales,
            "ev": ev,
            "debt": debt,
            "cash": cash,
            "revenue": ttm_rev,
            "shares": shares,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="ev_sales",
    per_share_label=None,        # Type 2 fundamental ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="EV/Receita",
    ratio_key="ev_sales",
    ratio_fn=ev_sales_at,
    history_fn=ev_sales_history,
    engines=["price", "shares", "debt", "cash", "revenue"],
    category="valuation",
    aliases=["ev_receita", "ev_vendas", "evs"],
))
