"""metrics/rps.py -- RPS (Receita Por Ação) + PSR (Price-to-Sales) metric.

RPS = revenue / shares             (per-share value, from revenue + shares engines)
PSR = price / RPS                  (price ratio, adds price engine)

This metric produces BOTH:
  - RPS (per-share value): revenue per share, useful on its own
  - PSR (price ratio):     tells you if the stock is cheap vs history

Engines composed: price + revenue + shares

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.rps import rps_at, psr_at, rps_history
    rps = rps_at("PETR4", "2024-06-30")   # -> 21.54
    psr = psr_at("PETR4", "2024-06-30")   # -> 1.79
    h   = rps_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Per-share value: RPS = revenue / shares ----------------------------------

def rps_at(company: str, date: str) -> float | None:
    """Compute RPS (Receita Por Ação = revenue per share) at a specific date.

    RPS = TTM net revenue / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        RPS in BRL, or None if revenue or shares are missing/zero.
    """
    revenue = revenue_at(company, date)
    if revenue is None or revenue == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return revenue / shares


# -- Price ratio: PSR = price / RPS -------------------------------------------

def psr_at(company: str, date: str) -> float | None:
    """Compute PSR (Price-to-Sales Ratio) at a specific date.

    PSR = price / RPS = price / (TTM revenue / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        PSR ratio as float, or None if any component is missing or RPS <= 0.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    rps = rps_at(company, date)
    if rps is None or rps <= 0:
        return None  # No revenue -- PSR is meaningless

    return price / rps


# -- History: daily series with RPS + PSR -------------------------------------

def rps_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily RPS + PSR time series for a date range.

    Optimized: TTM revenue changes only when new ITR/DFP is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all TTM revenue periods (step function -- ~4 per year)
    2. Get all shares periods (step function -- ~1 per year)
    3. For each daily price, find the most recent TTM revenue + shares
    4. Compute RPS = TTM revenue / shares, then PSR = price / RPS

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ttm_rev", "shares", "rps", "psr"}
        sorted oldest-first. Entries with None RPS/PSR (no revenue,
        missing data) are included with rps=None, psr=None so charts
        show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM revenue periods (quarterly step function)
    revenue_periods_list = revenue_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM revenue <= date
        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute RPS = TTM revenue / shares
        rps = None
        if ttm_rev is not None and ttm_rev > 0 and shares is not None and shares > 0:
            rps = ttm_rev / shares

        # Compute PSR = price / RPS
        psr = None
        if rps is not None and rps > 0 and price > 0:
            psr = price / rps

        result.append({
            "date": date,
            "price": price,
            "ttm_rev": ttm_rev,
            "shares": shares,
            "rps": rps,
            "psr": psr,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="rps",
    per_share_label="RPS",
    per_share_key="rps",
    per_share_fn=rps_at,
    ratio_label="PSR",
    ratio_key="psr",
    ratio_fn=psr_at,
    history_fn=rps_history,
    engines=["price", "revenue", "shares"],
    category="per_share",
    aliases=["psr", "p/sr", "price_sales", "preco_venda", "p_venda"],
))
