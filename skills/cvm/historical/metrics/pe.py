"""metrics/pe.py — P/L (Price-to-Earnings) historical metric.

P/L = price / (TTM earnings / shares)
    = price / EPS
    = price × shares / TTM earnings

This module imports the price, earnings, and shares engines and combines them.
Each engine is standalone — this module is the composition layer.

Usage:
    from skills.cvm.historical.metrics.pe import pe_at, pe_history
    p = pe_at("PETR4", "2024-06-30")  # → 5.34
    h = pe_history("PETR4", "2024-01-01", "2024-12-31")  # → [{date, pe}, ...]
"""

from __future__ import annotations

from skills.cvm.historical.engines.price import price_at, price_series
from skills.cvm.historical.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.historical.engines.shares import shares_at, shares_periods


def pe_at(company: str, date: str) -> float | None:
    """Compute P/L at a specific date.

    P/L = price / (TTM earnings / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/L ratio as float, or None if any component is missing.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    eps = earnings / shares
    if eps <= 0:
        return None  # Negative earnings — P/L is meaningless

    return price / eps


def pe_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily P/L time series for a date range.

    Optimized: TTM earnings change only when new ITR/DFP is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all TTM earnings periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent TTM + shares
    4. Compute P/L = price / (TTM / shares)

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date": "YYYY-MM-DD", "price": float, "ttm_earnings": float,
                 "shares": int, "pe": float} sorted oldest-first.
        Entries with None PE (negative earnings, missing data) are included
        with pe=None so the chart shows gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM earnings periods (quarterly step function)
    earnings_periods = ttm_earnings_periods(company)
    # Filter to periods <= date_to (we need prior periods too, so don't filter date_from)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM earnings <= date
        ttm = None
        for ep in reversed(earnings_periods):
            if ep["date"] <= date:
                ttm = ep["ttm"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute P/L
        pe = None
        if ttm is not None and ttm > 0 and shares is not None and shares > 0 and price > 0:
            eps = ttm / shares
            if eps > 0:
                pe = price / eps

        result.append({
            "date": date,
            "price": price,
            "ttm_earnings": ttm,
            "shares": shares,
            "pe": pe,
        })

    return result
