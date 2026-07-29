"""metrics/lpa.py -- LPA (Lucro por Ação) + P/L (Price-to-Earnings) metric.

LPA = earnings / shares            (per-share value, from earnings + shares engines)
P/L = price / LPA                  (price ratio, adds price engine)

This metric produces BOTH:
  - LPA (per-share value): useful on its own (e.g., backtest filters on EPS)
  - P/L (price ratio):     tells you if the stock is cheap vs history

Engines composed: price + earnings + shares

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.lpa import lpa_at, pe_at, lpa_history
    eps = lpa_at("PETR4", "2024-06-30")    # -> 10.35
    pl  = pe_at("PETR4", "2024-06-30")     # -> 4.75
    h   = lpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: LPA = earnings / shares ─────────────────────────────────

def lpa_at(company: str, date: str) -> float | None:
    """Compute LPA (Lucro por Ação = earnings per share) at a specific date.

    LPA = TTM earnings / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        LPA in BRL, or None if earnings or shares are missing/zero.
    """
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return earnings / shares


# ── Price ratio: P/L = price / LPA ───────────────────────────────────────────

def pe_at(company: str, date: str) -> float | None:
    """Compute P/L (Price-to-Earnings) at a specific date.

    P/L = price / LPA = price / (TTM earnings / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/L ratio as float, or None if any component is missing or LPA <= 0.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    lpa = lpa_at(company, date)
    if lpa is None or lpa <= 0:
        return None  # Negative earnings → P/L is meaningless

    return price / lpa


# ── History: daily series with LPA + P/L ─────────────────────────────────────

def lpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily LPA + P/L time series for a date range.

    Optimized: TTM earnings change only when new ITR/DFP is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all TTM earnings periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent TTM + shares
    4. Compute LPA = TTM / shares, then P/L = price / LPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ttm_earnings", "shares", "lpa", "pe"}
        sorted oldest-first. Entries with None LPA/PE (negative earnings,
        missing data) are included with lpa=None, pe=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM earnings periods (quarterly step function)
    earnings_periods = ttm_earnings_periods(company)

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

        # Compute LPA = TTM / shares
        lpa = None
        if ttm is not None and ttm > 0 and shares is not None and shares > 0:
            lpa = ttm / shares

        # Compute P/L = price / LPA
        pe = None
        if lpa is not None and lpa > 0 and price > 0:
            pe = price / lpa

        result.append({
            "date": date,
            "price": price,
            "ttm_earnings": ttm,
            "shares": shares,
            "lpa": lpa,
            "pe": pe,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="lpa",
    per_share_label="LPA",
    per_share_key="lpa",
    per_share_fn=lpa_at,
    ratio_label="P/L",
    ratio_key="pe",
    ratio_fn=pe_at,
    history_fn=lpa_history,
    engines=["price", "earnings", "shares"],
    category="per_share",
    aliases=["pe", "pl", "p/l", "preco_lucro"],
))
