"""metrics/graham_number.py -- Graham Number (Benjamin Graham intrinsic value) metric.

Graham Number = sqrt(22.5 × EPS × VPA)
              = sqrt(22.5 × LPA × VPA)

Where:
  LPA = earnings / shares   (Lucro por Ação, from earnings + shares engines)
  VPA = PL / shares         (Valor Patrimonial por Ação, from pl + shares engines)

The 22.5 constant = 15 × 1.5, Graham's recommended maximum P/L (15) and
P/VPA (1.5) for a defensive investor. The Graham Number is the price
above which a stock would violate BOTH limits simultaneously.

This is a FUNDAMENTAL RATIO (like ROE) -- it does NOT use the price engine.
It's a price TARGET, not a price ratio. The output is in BRL (a price),
not a dimensionless multiple.

Mirrors metrics/roe.py:
  - per_share_label=None (fundamental ratio -- no per-share value)
  - Uses the union of period dates from its engines as the date axis
  - Returns None when input values are <= 0 (negative earnings or equity)
  - Difference from roe: also uses the shares engine (for LPA + VPA derivation)

Engines composed: earnings + pl + shares

Interpretation:
  - Price < Graham Number: undervalued (margin of safety)
  - Price > Graham Number: overvalued
  - Graham Number = None when LPA <= 0 or VPA <= 0 (negative earnings or
    equity -- Graham formula meaningless, since you can't take sqrt of
    a negative product)
  - Graham Number is a conservative intrinsic value estimate; modern
    practitioners often treat it as a "fair value ceiling" rather than
    a strict buy/sell signal

NOTE: The Graham Number does NOT use the price engine at registration
time, but downstream consumers (charts, summary) may overlay the price
series for comparison against the Graham Number. The history_fn below
returns only the Graham Number + its inputs.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.graham_number import graham_number_at, graham_number_history
    g = graham_number_at("PETR4", "2024-06-30")   # -> 38.45 (BRL price target)
    h = graham_number_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# Graham's constant: 22.5 = 15 (max P/L) × 1.5 (max P/VPA)
GRAHAM_CONSTANT = 22.5


# -- Ratio: Graham Number = sqrt(22.5 × LPA × VPA) ---------------------------

def graham_number_at(company: str, date: str) -> float | None:
    """Compute Graham Number (Benjamin Graham intrinsic value) at a specific date.

    Graham Number = sqrt(22.5 × LPA × VPA)
                  = sqrt(22.5 × (earnings / shares) × (pl / shares))

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Graham Number in BRL (a price target), or None if:
        - earnings is None or <= 0 (negative earnings -- LPA <= 0, sqrt of
          negative product undefined)
        - PL is None or <= 0 (negative equity -- VPA <= 0, sqrt of negative
          product undefined)
        - shares is None or <= 0 (no shares outstanding)
    """
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None  # Negative/zero earnings → LPA <= 0 → sqrt undefined

    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None  # Negative/zero equity → VPA <= 0 → sqrt undefined

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    lpa = earnings / shares
    vpa = pl / shares

    # Defensive: lpa > 0 and vpa > 0 guaranteed by checks above, but
    # guard against floating-point edge cases.
    product = GRAHAM_CONSTANT * lpa * vpa
    if product <= 0:
        return None

    return product ** 0.5


# -- History: step-function series with Graham Number -------------------------

def graham_number_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute Graham Number time series for a date range.

    The Graham Number changes when earnings (quarterly), PL (quarterly), or
    shares (annual) change. Since it has no daily driver (no price), we
    produce a series based on the union of earnings + pl + shares period
    dates. Between those dates, the Graham Number is constant (step function).

    This gives ~4-8 data points per year (quarterly earnings + quarterly PL
    + annual shares, with overlap).

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "graham_number", "lpa", "vpa", "earnings", "pl",
                 "shares"} sorted oldest-first.
        Entries with None Graham Number (negative earnings/equity, missing
        data) are included with graham_number=None so charts show gaps.
    """
    # Get TTM earnings periods (quarterly step function)
    earnings_periods = ttm_earnings_periods(company)

    # Get PL periods (quarterly step function)
    pl_periods_list = pl_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    # Build a union of all dates from the three engines
    all_dates = set()
    for ep in earnings_periods:
        if date_from <= ep["date"] <= date_to:
            all_dates.add(ep["date"])
    for pp in pl_periods_list:
        if date_from <= pp["date"] <= date_to:
            all_dates.add(pp["date"])
    for sp in sh_periods:
        if date_from <= sp["date"] <= date_to:
            all_dates.add(sp["date"])

    if not all_dates:
        return []

    # Sort oldest-first
    sorted_dates = sorted(all_dates)

    result = []
    for date in sorted_dates:
        # Find most recent TTM earnings <= date
        ttm = None
        for ep in reversed(earnings_periods):
            if ep["date"] <= date:
                ttm = ep["ttm"]
                break

        # Find most recent PL <= date
        pl = None
        for pp in reversed(pl_periods_list):
            if pp["date"] <= date:
                pl = pp["pl"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute LPA = earnings / shares
        lpa = None
        if ttm is not None and shares is not None and shares > 0:
            lpa = ttm / shares

        # Compute VPA = PL / shares
        vpa = None
        if pl is not None and shares is not None and shares > 0:
            vpa = pl / shares

        # Compute Graham Number = sqrt(22.5 × LPA × VPA)
        graham = None
        if (lpa is not None and lpa > 0
            and vpa is not None and vpa > 0):
            product = GRAHAM_CONSTANT * lpa * vpa
            if product > 0:
                graham = product ** 0.5

        result.append({
            "date": date,
            "graham_number": graham,
            "lpa": lpa,
            "vpa": vpa,
            "earnings": ttm,
            "pl": pl,
            "shares": shares,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="graham_number",
    per_share_label=None,        # Fundamental ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="Graham Number",
    ratio_key="graham_number",
    ratio_fn=graham_number_at,
    history_fn=graham_number_history,
    engines=["earnings", "pl", "shares"],
    aliases=["graham", "numero_graham"],
))
