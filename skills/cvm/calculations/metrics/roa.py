"""metrics/roa.py -- ROA (Return on Assets) fundamental ratio metric.

ROA = TTM earnings / Ativo Total
   = Lucro Líquido / Total Assets

ROA is a FUNDAMENTAL RATIO -- it measures how efficiently a company uses
its total assets to generate profit. Like ROE, it does NOT use the price
or shares engines. Composes only earnings + total_assets engines.

NOTE (v1.2 fix): Previously imported `assets_at` (codigo 1.01 = Ativo
Circulante / current assets), which silently overstated ROA by ~2-5x
since current assets are typically a fraction of total assets. Now
imports `total_assets_at` (codigo 1 = Ativo Total, the true total).

Engines composed: earnings + total_assets

Interpretation:
  - ROA > 5%:  good
  - ROA > 10%: excellent
  - ROA < 2%:  mediocre (asset-heavy or low-margin business)
  - ROA < 0%:  company is losing money

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.roa import roa_at, roa_history
    r = roa_at("PETR4", "2024-06-30")    # -> 0.15 (15%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.bpa.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Ratio: ROA = earnings / total_assets -------------------------------------

def roa_at(company: str, date: str) -> float | None:
    """Compute ROA (Return on Assets) at a specific date.

    ROA = TTM earnings / Ativo Total (codigo 1, total assets)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROA as a fraction (0.15 = 15%), or None if:
        - earnings is None or <= 0 (negative earnings -- ROA meaningless)
        - total_assets is None or <= 0 (zero assets -- ROA meaningless)
    """
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None

    total_assets = total_assets_at(company, date)
    if total_assets is None or total_assets <= 0:
        return None

    return earnings / total_assets


# -- History: series with ROA (no price, no shares) ---------------------------

def roa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute ROA time series for a date range.

    ROA changes only when earnings (quarterly) or total_assets (quarterly)
    change. No daily price driver -- series based on union of earnings +
    total_assets period dates. ~4-8 data points per year.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "roa", "ttm_earnings", "total_assets"} sorted
        oldest-first. Entries with None ROA (negative earnings/assets,
        missing data) are included with roa=None so charts show gaps.
    """
    earnings_periods = ttm_earnings_periods(company)
    ta_periods_list = total_assets_periods(company)

    all_dates = set()
    for ep in earnings_periods:
        if date_from <= ep["date"] <= date_to:
            all_dates.add(ep["date"])
    for tap in ta_periods_list:
        if date_from <= tap["date"] <= date_to:
            all_dates.add(tap["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)

    result = []
    for date in sorted_dates:
        ttm = None
        for ep in reversed(earnings_periods):
            if ep["date"] <= date:
                ttm = ep["ttm"]
                break

        total_assets = None
        for tap in reversed(ta_periods_list):
            if tap["date"] <= date:
                total_assets = tap["total_assets"]
                break

        roa = None
        if (ttm is not None and ttm > 0
            and total_assets is not None and total_assets > 0):
            roa = ttm / total_assets

        result.append({
            "date": date,
            "roa": roa,
            "ttm_earnings": ttm,
            "total_assets": total_assets,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="roa",
    per_share_label=None,
    per_share_key=None,
    per_share_fn=None,
    ratio_label="ROA",
    ratio_key="roa",
    ratio_fn=roa_at,
    history_fn=roa_history,
    engines=["earnings", "total_assets"],
    category="profitability",
    aliases=["return_on_assets", "retorno_ativos"],
))
