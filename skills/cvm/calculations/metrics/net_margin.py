"""metrics/net_margin.py -- Net Margin fundamental ratio metric.

Net Margin = TTM earnings / TTM revenue
           = Lucro Líquido / Receita Líquida

Measures how much of each BRL of revenue becomes profit. Fundamental ratio
(no price, no shares). Composes earnings + revenue engines.

Interpretation:
  - Net Margin > 20%: excellent
  - Net Margin 10-20%: good
  - Net Margin < 5%: low margin
  - Net Margin < 0%: company is losing money

Usage:
    from skills.cvm.calculations.metrics.net_margin import net_margin_at
    m = net_margin_at("PETR4", "2024-06-30")  # -> 0.25 (25%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.revenue import revenue_at, revenue_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def net_margin_at(company: str, date: str) -> float | None:
    """Net Margin = TTM earnings / TTM revenue."""
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    return earnings / revenue


def net_margin_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Net Margin time series — union of earnings + revenue period dates."""
    earnings_periods = ttm_earnings_periods(company)
    revenue_periods_list = revenue_periods(company)

    all_dates = set()
    for periods in [earnings_periods, revenue_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm = None
        for ep in reversed(earnings_periods):
            if ep["date"] <= date:
                ttm = ep["ttm"]
                break
        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break
        net_margin = None
        if ttm is not None and ttm > 0 and ttm_rev is not None and ttm_rev > 0:
            net_margin = ttm / ttm_rev
        result.append({"date": date, "net_margin": net_margin, "ttm_earnings": ttm, "ttm_rev": ttm_rev})
    return result


register_metric(MetricSpec(
    name="net_margin",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Margem Líquida",
    ratio_key="net_margin",
    ratio_fn=net_margin_at,
    history_fn=net_margin_history,
    engines=["earnings", "revenue"],
    category="profitability",
    aliases=["nm", "margem_liquida", "ml", "net_margin_pct"],
))
