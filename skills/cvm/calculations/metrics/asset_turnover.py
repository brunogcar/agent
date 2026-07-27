"""metrics/asset_turnover.py -- Asset Turnover fundamental ratio metric.

Asset Turnover = TTM Revenue / Total Assets
               = Receita Líquida / Ativo Total

Measures how efficiently a company uses its assets to generate revenue.
Fundamental ratio (no price, no shares). Composes revenue + assets engines.

Interpretation:
  - Asset Turnover > 1.0: efficient (generates more revenue than assets)
  - Asset Turnover 0.5-1.0: moderate
  - Asset Turnover < 0.3: low (asset-heavy business like utilities)
  - High turnover + high margin = high ROA

Usage:
    from skills.cvm.calculations.metrics.asset_turnover import asset_turnover_at
    a = asset_turnover_at("PETR4", "2024-06-30")  # -> 0.75
"""
from __future__ import annotations

from skills.cvm.calculations.engines.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.assets import assets_at, assets_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def asset_turnover_at(company: str, date: str) -> float | None:
    """Asset Turnover = TTM Revenue / Total Assets."""
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    assets = assets_at(company, date)
    if assets is None or assets <= 0:
        return None
    return revenue / assets


def asset_turnover_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Asset Turnover time series — union of revenue + assets period dates."""
    revenue_periods_list = revenue_periods(company)
    assets_periods_list = assets_periods(company)

    all_dates = set()
    for periods in [revenue_periods_list, assets_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_rev = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break
        assets = None
        for ap in reversed(assets_periods_list):
            if ap["date"] <= date:
                assets = ap["assets"]
                break
        asset_turnover = None
        if (ttm_rev is not None and ttm_rev > 0
            and assets is not None and assets > 0):
            asset_turnover = ttm_rev / assets
        result.append({"date": date, "asset_turnover": asset_turnover,
                        "ttm_rev": ttm_rev, "assets": assets})
    return result


register_metric(MetricSpec(
    name="asset_turnover",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Giro de Ativos",
    ratio_key="asset_turnover",
    ratio_fn=asset_turnover_at,
    history_fn=asset_turnover_history,
    engines=["revenue", "assets"],
    aliases=["at", "giro_ativos", "asset_turnover_ratio"],
))
