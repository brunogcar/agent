"""metrics/working_capital.py -- Working Capital (BRL value, not ratio).

Working Capital = Current Assets - Current Liabilities
                = Ativo Circulante - Passivo Circulante

Measures short-term operating liquidity -- the buffer a company has to
fund day-to-day operations after paying short-term obligations.

Unlike most other metrics in this skill, Working Capital is a BRL VALUE
(not a dimensionless ratio). It can be NEGATIVE -- that's valid (negative
working capital is common for high-turnover retailers like supermarkets
that collect from customers faster than they pay suppliers). Negative
working capital is NOT an error condition.

This is a Type 2 metric (no per-share value, no price). per_share_*=None.
The ratio_key is `working_capital` (the BRL value is exposed as the
"ratio" field, even though it's not a ratio -- this matches the
Type 2 fundamental ratio pattern).

Engines composed: current_assets + current_liabilities

Interpretation:
  - Working Capital > 0: company can cover short-term obligations
  - Working Capital < 0: company relies on operating cash flow to cover
    short-term obligations (common for retailers, red flag for others)
  - Working Capital = None when either component is missing
  - Large positive WC may indicate inefficient cash use (excess inventory,
    slow-paying receivables)

Usage:
    from skills.cvm.calculations.metrics.working_capital import working_capital_at
    w = working_capital_at("PETR4", "2024-06-30")  # -> 50e9 (BRL, can be negative)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.current_assets import current_assets_at, current_assets_periods
from skills.cvm.calculations.engines.current_liabilities import (
    current_liabilities_at,
    current_liabilities_periods,
)
from skills.cvm.calculations._registry import MetricSpec, register_metric


def working_capital_at(company: str, date: str) -> float | None:
    """Working Capital = Current Assets - Current Liabilities.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Working Capital in BRL (can be negative -- valid), or None if
        either component is missing.
    """
    current_assets = current_assets_at(company, date)
    if current_assets is None:
        return None
    current_liab = current_liabilities_at(company, date)
    if current_liab is None:
        return None
    return current_assets - current_liab


def working_capital_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Working Capital time series -- union of current_assets + current_liabilities
    period dates.
    """
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
        for ap in reversed(assets_periods_list):
            if ap["date"] <= date:
                current_assets = ap["current_assets"]
                break
        current_liab = None
        for clp in reversed(cl_periods_list):
            if clp["date"] <= date:
                current_liab = clp["current_liabilities"]
                break
        working_capital = None
        if current_assets is not None and current_liab is not None:
            working_capital = current_assets - current_liab
        result.append({
            "date": date,
            "working_capital": working_capital,
            "current_assets": current_assets,
            "current_liabilities": current_liab,
        })
    return result


register_metric(MetricSpec(
    name="working_capital",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Capital de Giro",
    ratio_key="working_capital",
    ratio_fn=working_capital_at,
    history_fn=working_capital_history,
    engines=["current_assets", "current_liabilities"],
    aliases=["capital_giro", "giro", "wc"],
))
