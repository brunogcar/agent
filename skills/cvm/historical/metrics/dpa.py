"""metrics/dpa.py -- DPA (Dividends Per Share) + Div Yield + Payout metric.

DPA    = dividends_ttm                    (per-share value, from dividends engine)
DY     = DPA / price                      (price ratio, adds price engine)
Payout = DPA / LPA                        (auxiliary, exposed in series only)

The dividends engine returns rate already per-share (R$/share), so DPA is
just the TTM sum of rates in the trailing 365-day window. No division by
shares outstanding is needed for DPA itself. (Shares is still composed
because Payout uses LPA = earnings/shares.)

This metric produces BOTH:
  - DPA (per-share value): trailing 12 months dividends per share
  - Div Yield (price ratio): DPA / price -- tells you the income yield

Engines composed: price + dividends + earnings + shares

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.metrics.dpa import dpa_at, dy_at, payout_at, dpa_history
    dpa  = dpa_at("PETR4", "2024-06-30")    # -> 1.85 (R$/share TTM)
    dy   = dy_at("PETR4", "2024-06-30")     # -> 0.048 (4.8%)
    pay  = payout_at("PETR4", "2024-06-30") # -> 0.42 (42% of earnings)
    h    = dpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.historical.engines.price import price_at, price_series
from skills.cvm.historical.engines.dividends import dividends_at, dividends_periods
from skills.cvm.historical.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.historical.engines.shares import shares_at, shares_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


# ── Per-share value: DPA = trailing 12 months dividends per share ────────────

def dpa_at(company: str, date: str) -> float | None:
    """Compute DPA (Dividends Per Share, TTM) at a specific date.

    DPA = SUM(cash_dividends.rate WHERE event_date in [date-365, date])

    The dividends engine returns rate already per-share (R$/share), so no
    division by shares outstanding is needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        DPA TTM in BRL per share, or None if no dividends data.
        Returns 0.0 if the company pays no dividends (different from None
        which means "no data available").
    """
    return dividends_at(company, date)


# ── Price ratio: Div Yield = DPA / price ─────────────────────────────────────

def dy_at(company: str, date: str) -> float | None:
    """Compute Dividend Yield at a specific date.

    Div Yield = DPA TTM / price

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Div Yield as a fraction (0.05 = 5%), or None if DPA or price missing.
        Returns 0.0 if DPA is 0 (company pays no dividends -- yield is 0,
        not None).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    dpa = dpa_at(company, date)
    if dpa is None:
        return None  # No dividends data at all -- can't compute yield

    # dpa == 0.0 (company pays no dividends) -> yield = 0.0
    return dpa / price


# ── Auxiliary: Payout = DPA / LPA ────────────────────────────────────────────

def payout_at(company: str, date: str) -> float | None:
    """Compute Payout ratio at a specific date.

    Payout = DPA TTM / LPA TTM

    Payout tells you what fraction of earnings is being returned to
    shareholders as dividends. >1.0 means the company is paying out more
    than it earns (unsustainable).

    Note: payout is exposed as a function and included in dpa_history()
    series entries, but is NOT the main ratio of this metric. The metric's
    main ratio is Div Yield. "payout" is registered as an alias so
    ratio_history(metric="payout") dispatches to the dpa metric.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Payout as a fraction (0.5 = 50%), or None if DPA or LPA is missing
        or LPA <= 0 (negative earnings -- payout is meaningless).
    """
    dpa = dpa_at(company, date)
    if dpa is None:
        return None

    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None  # Negative/zero earnings -> payout meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    lpa = earnings / shares
    if lpa <= 0:
        return None

    return dpa / lpa


# ── History: daily series with DPA + Div Yield + Payout ──────────────────────

def dpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily DPA + Div Yield time series for a date range.

    Optimized: DPA changes only on dividend event dates (a few times per year).
    TTM earnings change quarterly. Shares change annually. Price changes daily.
    So we:
    1. Get all DPA periods (step function -- changes on event dates)
    2. Get all TTM earnings periods (step function -- quarterly)
    3. Get all shares periods (step function -- annual)
    4. For each daily price, find the most recent DPA + TTM + shares
    5. Compute Div Yield = DPA / price, Payout = DPA / LPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "dpa", "dy", "payout",
                 "ttm_earnings", "shares"}
        sorted oldest-first. Entries with None (missing data) are included
        so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get DPA periods (step function -- changes on dividend event dates)
    dpa_periods = dividends_periods(company)

    # Get TTM earnings periods (quarterly step function)
    earnings_periods = ttm_earnings_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent DPA <= date (step function)
        dpa = None
        for dp in reversed(dpa_periods):
            if dp["date"] <= date:
                dpa = dp["dpa"]
                break

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

        # Compute Div Yield = DPA / price
        dy = None
        if dpa is not None and price > 0:
            dy = dpa / price

        # Compute LPA = TTM / shares (needed for Payout)
        lpa = None
        if ttm is not None and ttm > 0 and shares is not None and shares > 0:
            lpa = ttm / shares

        # Compute Payout = DPA / LPA
        payout = None
        if dpa is not None and lpa is not None and lpa > 0:
            payout = dpa / lpa

        result.append({
            "date": date,
            "price": price,
            "dpa": dpa,
            "dy": dy,
            "payout": payout,
            "ttm_earnings": ttm,
            "shares": shares,
            "lpa": lpa,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="dpa",
    per_share_label="DPA",
    per_share_key="dpa",
    per_share_fn=dpa_at,
    ratio_label="Div Yield",
    ratio_key="dy",
    ratio_fn=dy_at,
    history_fn=dpa_history,
    engines=["price", "dividends", "earnings", "shares"],
    aliases=["dy", "dividend_yield", "yld", "payout"],
))
