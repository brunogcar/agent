"""metrics/earnings_yield.py -- Earnings Yield metric.

Earnings Yield = EPS / price = 1 / P/L

Tells you the earnings return per dollar invested. Useful for comparing
stocks vs bonds (e.g., if EY > Selic, stock is "cheap" vs risk-free rate).

This is a FUNDAMENTAL RATIO — composes 3 engines: price + earnings + shares.
It's the inverse of P/L, but registered as a separate metric so it appears
in compute_all_ratios() and can be charted independently.

Engines composed: price + earnings + shares

Interpretation:
  - EY > 10%:   cheap (high earnings relative to price)
  - EY 6-10%:   fair
  - EY 3-6%:    expensive
  - EY < 3%:    very expensive
  - EY = None when earnings <= 0 or price <= 0

Usage:
    from skills.cvm.calculations.metrics.earnings_yield import earnings_yield_at
    ey = earnings_yield_at("PETR4", "2024-06-30")   # -> 0.085 (8.5%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def earnings_yield_at(company: str, date: str) -> float | None:
    """Compute Earnings Yield at a specific date.

    Earnings Yield = TTM EPS / price = (TTM earnings / shares) / price

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Earnings Yield as a fraction (0.085 = 8.5%), or None if earnings
        <= 0, price <= 0, or any component missing.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    eps = earnings / shares
    return eps / price


def earnings_yield_history(
    company: str, date_from: str, date_to: str,
) -> list[dict]:
    """Build a historical Earnings Yield time series.

    Merges the price series (daily) with the earnings + shares series
    (quarterly step function). At each date, computes EPS / price.

    Args:
        company: Ticker, name, or CNPJ.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).

    Returns:
        List of ``{"date": str, "earnings_yield": float | None}`` dicts,
        sorted oldest-first. Dates with missing data have None.
    """
    # Get all dates from all 3 sources.
    price_pts = price_series(company, date_from, date_to)
    earnings_pts = ttm_earnings_periods(company, date_from, date_to)
    shares_pts = shares_periods(company, date_from, date_to)

    # Build step-function lookups for earnings + shares (quarterly → daily).
    # earnings_pts/shares_pts are [{date, value}] sorted oldest-first.
    # For each price date, find the most recent earnings/shares value.
    def _step_lookup(pts: list[dict], target_date: str) -> float | None:
        """Return the most recent value at or before target_date."""
        result = None
        for p in pts:
            if p.get("date", "") <= target_date:
                result = p.get("value")
            else:
                break
        return result

    result: list[dict] = []
    for p in price_pts:
        d = p.get("date", "")
        price = p.get("close") or p.get("value")
        if price is None or price <= 0:
            result.append({"date": d, "earnings_yield": None})
            continue

        earnings = _step_lookup(earnings_pts, d)
        shares = _step_lookup(shares_pts, d)

        if earnings is None or earnings <= 0 or shares is None or shares <= 0:
            result.append({"date": d, "earnings_yield": None})
            continue

        eps = earnings / shares
        result.append({"date": d, "earnings_yield": eps / price})

    return result


register_metric(MetricSpec(
    name="earnings_yield",
    ratio_label="Earnings Yield",
    ratio_key="earnings_yield",
    ratio_fn=earnings_yield_at,
    history_fn=earnings_yield_history,
    engines=["price", "earnings", "shares"],
    category="valuation",
    aliases=["ey", "rendimento_lucro"],
    tooltip="Earnings Yield = EPS / Preço = 1 / P/L. Retorno de lucro por R$ investido. >10% barato, 6-10% justo, <3% caro.",
))
