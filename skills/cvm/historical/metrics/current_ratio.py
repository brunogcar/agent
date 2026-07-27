"""metrics/current_ratio.py -- Current Ratio fundamental ratio metric.

Current Ratio = Current Assets / Current Liabilities
              = Ativo Circulante / Passivo Circulante

Measures short-term liquidity — ability to pay short-term obligations.
Fundamental ratio (no price, no shares). Composes assets + current_liabilities.

NOTE: The `assets` engine queries BPA codigo 1.01 which is "Ativo Circulante"
(current assets), NOT "Ativo Total" (total assets, code "1"). This is correct
for the current ratio — we want current assets here. The `total_assets` engine
(code "1") is used by ROA for the actual total assets.

Interpretation:
  - Current Ratio > 2.0: very liquid (may indicate inefficient cash use)
  - Current Ratio 1.0-2.0: healthy
  - Current Ratio < 1.0: potential liquidity risk
  - Current Ratio < 0.5: high risk of short-term default

Usage:
    from skills.cvm.historical.metrics.current_ratio import current_ratio_at
    c = current_ratio_at("PETR4", "2024-06-30")  # -> 1.5
"""
from __future__ import annotations

from skills.cvm.historical.engines.assets import assets_at, assets_periods
from skills.cvm.historical.engines.current_liabilities import current_liabilities_at, current_liabilities_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


def current_ratio_at(company: str, date: str) -> float | None:
    """Current Ratio = Current Assets / Current Liabilities."""
    current_assets = assets_at(company, date)
    if current_assets is None or current_assets <= 0:
        return None
    current_liab = current_liabilities_at(company, date)
    if current_liab is None or current_liab <= 0:
        return None
    return current_assets / current_liab


def current_ratio_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Current Ratio time series — union of assets + current_liabilities dates."""
    assets_periods_list = assets_periods(company)
    cl_periods_list = current_liabilities_periods(company)

    all_dates = set()
    for periods in [assets_periods_list, cl_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        current_assets = None
        for ap in reversed(assets_periods_list):
            if ap["date"] <= date:
                current_assets = ap["assets"]
                break
        current_liab = None
        for clp in reversed(cl_periods_list):
            if clp["date"] <= date:
                current_liab = clp["current_liabilities"]
                break
        current_ratio = None
        if (current_assets is not None and current_assets > 0
            and current_liab is not None and current_liab > 0):
            current_ratio = current_assets / current_liab
        result.append({"date": date, "current_ratio": current_ratio,
                        "current_assets": current_assets, "current_liabilities": current_liab})
    return result


register_metric(MetricSpec(
    name="current_ratio",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Liquidez Corrente",
    ratio_key="current_ratio",
    ratio_fn=current_ratio_at,
    history_fn=current_ratio_history,
    engines=["assets", "current_liabilities"],
    aliases=["liquidez_corrente", "cr", "current_liquidity"],
))
