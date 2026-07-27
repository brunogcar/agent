"""metrics/capex_revenue.py -- CapEx/Revenue fundamental ratio metric.

CapEx/Revenue = TTM CapEx / TTM Revenue
              = Investimentos / Receita Líquida

Measures capital intensity — how much of each BRL of revenue is reinvested
in fixed/intangible assets. CapEx values are typically NEGATIVE (cash
outflow), so the ratio is typically negative.

Fundamental ratio (no price, no shares). Composes capex + revenue engines.

Interpretation:
  - CapEx/Revenue < -20%: very capital-intensive (utilities, telecom)
  - CapEx/Revenue -5% to -20%: moderate capital intensity
  - CapEx/Revenue > -5%: low capital intensity (services, software)
  - CapEx/Revenue near 0: minimal reinvestment (may indicate underinvestment)

Usage:
    from skills.cvm.historical.metrics.capex_revenue import capex_revenue_at
    c = capex_revenue_at("PETR4", "2024-06-30")  # -> -0.15 (-15%)
"""
from __future__ import annotations

from skills.cvm.historical.engines.capex import capex_at, capex_periods
from skills.cvm.historical.engines.revenue import revenue_at, revenue_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


def capex_revenue_at(company: str, date: str) -> float | None:
    """CapEx/Revenue = TTM CapEx / TTM Revenue."""
    capex = capex_at(company, date)
    if capex is None:
        return None
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    return capex / revenue


def capex_revenue_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """CapEx/Revenue time series — union of capex + revenue period dates."""
    capex_periods_list = capex_periods(company)
    revenue_periods_list = revenue_periods(company)

    all_dates = set()
    for periods in [capex_periods_list, revenue_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_capex = None
        for cp in reversed(capex_periods_list):
            if cp["date"] <= date:
                ttm_capex = cp["ttm_capex"]
                break
        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break
        capex_revenue = None
        if ttm_capex is not None and ttm_rev is not None and ttm_rev > 0:
            capex_revenue = ttm_capex / ttm_rev
        result.append({"date": date, "capex_revenue": capex_revenue,
                        "ttm_capex": ttm_capex, "ttm_rev": ttm_rev})
    return result


register_metric(MetricSpec(
    name="capex_revenue",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CapEx/Receita",
    ratio_key="capex_revenue",
    ratio_fn=capex_revenue_at,
    history_fn=capex_revenue_history,
    engines=["capex", "revenue"],
    aliases=["capex_intensity", "intensidade_capex"],
))
