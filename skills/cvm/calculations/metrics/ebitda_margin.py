"""metrics/ebitda_margin.py -- EBITDA Margin fundamental ratio metric.

EBITDA Margin = (EBIT + D&A) / Revenue
              = EBITDA / Receita Líquida

Measures operating profitability before D&A. Fundamental ratio (no price,
no shares). Composes ebit + da + revenue engines.

Interpretation:
  - EBITDA Margin > 30%: excellent
  - EBITDA Margin 15-30%: good
  - EBITDA Margin < 10%: low

Usage:
    from skills.cvm.calculations.metrics.ebitda_margin import ebitda_margin_at
    m = ebitda_margin_at("PETR4", "2024-06-30")  # -> 0.35 (35%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dfc.da import da_at, da_periods
from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def ebitda_margin_at(company: str, date: str) -> float | None:
    """EBITDA Margin = (EBIT + D&A) / Revenue."""
    ebit = ebit_at(company, date)
    if ebit is None:
        return None
    da = da_at(company, date)
    if da is None:
        return None
    ebitda = ebit + da
    if ebitda <= 0:
        return None
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    return ebitda / revenue


def ebitda_margin_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """EBITDA Margin time series — union of ebit + da + revenue period dates."""
    ebit_periods_list = ebit_periods(company)
    da_periods_list = da_periods(company)
    revenue_periods_list = revenue_periods(company)

    all_dates = set()
    for periods in [ebit_periods_list, da_periods_list, revenue_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break
        ttm_da = None
        for dap in reversed(da_periods_list):
            if dap["date"] <= date:
                ttm_da = dap["ttm_da"]
                break
        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break
        ebitda = None
        if ttm_ebit is not None and ttm_da is not None:
            ebitda = ttm_ebit + ttm_da
        ebitda_margin = None
        if (ebitda is not None and ebitda > 0
            and ttm_rev is not None and ttm_rev > 0):
            ebitda_margin = ebitda / ttm_rev
        result.append({"date": date, "ebitda_margin": ebitda_margin,
                        "ttm_ebit": ttm_ebit, "ttm_da": ttm_da, "ttm_rev": ttm_rev})
    return result


register_metric(MetricSpec(
    name="ebitda_margin",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Margem EBITDA",
    ratio_key="ebitda_margin",
    ratio_fn=ebitda_margin_at,
    history_fn=ebitda_margin_history,
    engines=["ebit", "da", "revenue"],
    category="profitability",
    aliases=["em", "margem_ebitda", "ebitda_margin_pct"],
))
