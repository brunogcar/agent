"""metrics/asset_turnover.py -- Asset Turnover fundamental ratio metric.

Asset Turnover = TTM Revenue / Total Assets
               = Receita Líquida / Ativo Total

Measures how efficiently a company uses its assets to generate revenue.
Fundamental ratio (no price, no shares). Composes revenue + total_assets.

NOTE (v1.2 fix): Previously imported `assets_at` (codigo 1.01 = Ativo
Circulante / current assets), which silently overstated Asset Turnover
by ~2-5x since current assets are typically a fraction of total assets.
Now imports `total_assets_at` (codigo 1 = Ativo Total, the true total).

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

from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.bpa.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def asset_turnover_at(company: str, date: str) -> float | None:
    """Asset Turnover = TTM Revenue / Total Assets (codigo 1)."""
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    total_assets = total_assets_at(company, date)
    if total_assets is None or total_assets <= 0:
        return None
    return revenue / total_assets


def asset_turnover_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Asset Turnover time series — union of revenue + total_assets dates."""
    revenue_periods_list = revenue_periods(company)
    ta_periods_list = total_assets_periods(company)

    all_dates = set()
    for periods in [revenue_periods_list, ta_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_rev = None
        ttm_rev = lookup_lte(revenue_periods_list, date, "ttm_rev")
        total_assets = None
        total_assets = lookup_lte(ta_periods_list, date, "total_assets")
        asset_turnover = None
        if (ttm_rev is not None and ttm_rev > 0
            and total_assets is not None and total_assets > 0):
            asset_turnover = ttm_rev / total_assets
        result.append({"date": date, "asset_turnover": asset_turnover,
                        "ttm_rev": ttm_rev, "total_assets": total_assets})
    return result


register_metric(MetricSpec(
    name="asset_turnover",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Giro de Ativos",
    ratio_key="asset_turnover",
    ratio_fn=asset_turnover_at,
    history_fn=asset_turnover_history,
    engines=["revenue", "total_assets"],
    category="efficiency",
    aliases=["at", "giro_ativos", "asset_turnover_ratio"],
))
