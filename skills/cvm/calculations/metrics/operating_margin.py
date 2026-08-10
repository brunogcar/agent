"""metrics/operating_margin.py -- Operating Margin fundamental ratio metric.

Operating Margin = TTM EBIT / TTM revenue
                 = EBIT / Receita Líquida

Operating Margin is a FUNDAMENTAL RATIO -- it measures operating
profitability (before financial results and taxes). Does NOT use price or
shares engines. Composes only ebit + revenue engines.

Engines composed: ebit + revenue

Interpretation:
  - Operating Margin > 20%: high (tech, pharma)
  - Operating Margin 10-20%: good
  - Operating Margin < 5%: low (competitive/commodity business)
  - Operating Margin < 0%: operating losses

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.operating_margin import operating_margin_at, operating_margin_history
    o = operating_margin_at("PETR4", "2024-06-30")    # -> 0.25 (25%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# -- Ratio: Operating Margin = EBIT / revenue --------------------------------

def operating_margin_at(company: str, date: str) -> float | None:
    """Compute Operating Margin at a specific date.

    Operating Margin = TTM EBIT / TTM revenue

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Operating Margin as a fraction (0.25 = 25%), or None if:
        - EBIT is None or <= 0 (operating losses -- margin meaningless)
        - revenue is None or <= 0 (zero revenue)
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit <= 0:
        return None

    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None

    return ebit / revenue


# -- History: series with Operating Margin (no price, no shares) --------------

def operating_margin_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute Operating Margin time series for a date range.

    Operating Margin changes only when EBIT or revenue change (quarterly).
    No daily price driver -- series based on union of period dates.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "operating_margin", "ttm_ebit", "ttm_rev"} sorted oldest-first.
    """
    ebit_periods_list = ebit_periods(company)
    rev_periods = revenue_periods(company)

    all_dates = set()
    for ep in ebit_periods_list:
        if date_from <= ep["date"] <= date_to:
            all_dates.add(ep["date"])
    for rp in rev_periods:
        if date_from <= rp["date"] <= date_to:
            all_dates.add(rp["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)

    result = []
    for date in sorted_dates:
        ttm_ebit = None
        ttm_ebit = lookup_lte(ebit_periods_list, date, "ttm_ebit")

        ttm_rev = None
        ttm_rev = lookup_lte(rev_periods, date, "ttm_rev")

        operating_margin = None
        if (ttm_ebit is not None and ttm_ebit > 0
            and ttm_rev is not None and ttm_rev > 0):
            operating_margin = ttm_ebit / ttm_rev

        result.append({
            "date": date,
            "operating_margin": operating_margin,
            "ttm_ebit": ttm_ebit,
            "ttm_rev": ttm_rev,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="operating_margin",
    per_share_label=None,
    per_share_key=None,
    per_share_fn=None,
    ratio_label="Margem Operacional",
    ratio_key="operating_margin",
    ratio_fn=operating_margin_at,
    history_fn=operating_margin_history,
    engines=["ebit", "revenue"],
    category="profitability",
    aliases=["margem_operacional", "margem_ebit", "om", "operating_margin_pct"],
))
