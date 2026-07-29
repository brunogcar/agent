"""metrics/roe.py -- ROE (Return on Equity) fundamental ratio metric.

ROE = TTM earnings / Patrimônio Líquido
    = Lucro Líquido / PL

ROE is a FUNDAMENTAL RATIO -- it measures how efficiently a company uses
shareholders' equity to generate profit. Unlike per-share metrics (LPA, VPA)
and price ratios (P/L, P/VPA), ROE:
  - Does NOT use the price engine (no market price needed)
  - Does NOT use the shares engine (no shares outstanding needed)
  - Composes only earnings + pl engines

This is the first metric with per_share_label=None. The chart adapter
produces a single-dataset chart (just ROE over time, single axis). The
summary adapter skips the per-share KPI/row.

Engines composed: earnings + pl

Interpretation:
  - ROE > 15%: good (efficient equity use)
  - ROE > 20%: excellent
  - ROE < 10%: mediocre
  - ROE < 0%:  company is losing money (negative earnings)
  - ROE > 100%: possible red flag (earnings > PL, or PL very small)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.roe import roe_at, roe_history
    r = roe_at("PETR4", "2024-06-30")    # -> 0.35 (35%)
    h = roe_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Ratio: ROE = earnings / PL ----------------------------------------------

def roe_at(company: str, date: str) -> float | None:
    """Compute ROE (Return on Equity) at a specific date.

    ROE = TTM earnings / Patrimônio Líquido

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROE as a fraction (0.35 = 35%), or None if:
        - earnings is None or <= 0 (negative earnings -- ROE meaningless)
        - PL is None or <= 0 (negative equity -- ROE meaningless)
    """
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None  # Negative/zero earnings -> ROE meaningless

    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None  # Negative/zero equity -> ROE meaningless

    return earnings / pl


# -- History: daily series with ROE ------------------------------------------

def roe_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily ROE time series for a date range.

    ROE changes only when earnings (quarterly) or PL (quarterly) change.
    But since we don't have a daily "price" driver, we need a date axis.
    We use the PL periods as the date axis (each PL snapshot is a data point).

    Actually, for consistency with other metrics that produce daily series,
    we should produce a daily series. But ROE doesn't have a daily driver
    (no price). So we produce a series based on the union of earnings + PL
    period dates. Between those dates, ROE is constant (step function).

    This gives ~4-8 data points per year (quarterly earnings + quarterly PL).

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "roe", "ttm_earnings", "pl"} sorted oldest-first.
        Entries with None ROE (negative earnings/equity, missing data) are
        included with roe=None so charts show gaps.
    """
    # Get TTM earnings periods (quarterly step function)
    earnings_periods = ttm_earnings_periods(company)

    # Get PL periods (quarterly step function)
    pl_periods_list = pl_periods(company)

    # Build a union of all dates from both engines
    all_dates = set()
    for ep in earnings_periods:
        if date_from <= ep["date"] <= date_to:
            all_dates.add(ep["date"])
    for pp in pl_periods_list:
        if date_from <= pp["date"] <= date_to:
            all_dates.add(pp["date"])

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

        # Compute ROE = earnings / PL
        roe = None
        if (ttm is not None and ttm > 0
            and pl is not None and pl > 0):
            roe = ttm / pl

        result.append({
            "date": date,
            "roe": roe,
            "ttm_earnings": ttm,
            "pl": pl,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="roe",
    per_share_label=None,        # Fundamental ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="ROE",
    ratio_key="roe",
    ratio_fn=roe_at,
    history_fn=roe_history,
    engines=["earnings", "pl"],
    category="profitability",
    aliases=["return_on_equity", "retorno_pl", "retorno_patrimonio"],
))
