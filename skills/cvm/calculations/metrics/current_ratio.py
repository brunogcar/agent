"""metrics/current_ratio.py -- Current Ratio fundamental ratio metric.

Current Ratio = Current Assets / Current Liabilities
              = Ativo Circulante / Passivo Circulante

Measures short-term liquidity — ability to pay short-term obligations.
Fundamental ratio (no price, no shares). Composes current_assets +
current_liabilities engines.

Engines composed: current_assets + current_liabilities.

Interpretation:
  - Current Ratio > 2.0: very liquid (may indicate inefficient cash use)
  - Current Ratio 1.0-2.0: healthy
  - Current Ratio < 1.0: potential liquidity risk
  - Current Ratio < 0.5: high risk of short-term default

Usage:
    from skills.cvm.calculations.metrics.current_ratio import current_ratio_at
    c = current_ratio_at("PETR4", "2024-06-30")  # -> 1.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpa.current_assets import current_assets_at, current_assets_periods
from skills.cvm.calculations.engines.bpp.current_liabilities import current_liabilities_at, current_liabilities_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def current_ratio_at(company: str, date: str) -> float | None:
    """Current Ratio = Current Assets / Current Liabilities."""
    current_assets = current_assets_at(company, date)
    if current_assets is None or current_assets <= 0:
        return None
    current_liab = current_liabilities_at(company, date)
    if current_liab is None or current_liab <= 0:
        return None
    return current_assets / current_liab


def current_ratio_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Current Ratio time series — union of current_assets + current_liabilities dates."""
    assets_periods_list = current_assets_periods(company)
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
        current_assets = lookup_lte(assets_periods_list, date, "current_assets")
        current_liab = None
        current_liab = lookup_lte(cl_periods_list, date, "current_liabilities")
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
    engines=["current_assets", "current_liabilities"],
    category="liquidity",
    aliases=["liquidez_corrente", "cr", "current_liquidity"],
))
