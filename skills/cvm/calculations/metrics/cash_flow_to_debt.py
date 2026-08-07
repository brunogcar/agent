"""metrics/cash_flow_to_debt.py -- Cash Flow to Debt fundamental ratio metric.

Cash Flow to Debt = FCO / Total Debt
                  = Fluxo de Caixa Operacional / Dívida Total

Measures a company's ability to pay off all its debt using operating cash
flow alone (years to repay all debt at current FCO rate). Higher = stronger
ability to service debt.

Engines composed: operating_cf + debt

Interpretation:
  - CFD > 0.30 (30%): strong debt service capacity (can repay all debt in
    < 3.3 years from FCO alone)
  - CFD 0.10-0.30: moderate
  - CFD 0.05-0.10: tight (5-10 years to repay all debt from FCO alone)
  - CFD < 0.05: high leverage risk (> 20 years to repay)
  - CFD < 0: company is burning cash from operations (debt can only grow)
  - CFD = None when debt <= 0 (denominator guard)

Usage:
    from skills.cvm.calculations.metrics.cash_flow_to_debt import cash_flow_to_debt_at
    c = cash_flow_to_debt_at("PETR4", "2024-06-30")  # -> 0.42 (42%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def cash_flow_to_debt_at(company: str, date: str) -> float | None:
    """Cash Flow to Debt = FCO / Total Debt.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Cash Flow to Debt as a fraction (0.42 = 42%), or None if either
        component is missing or debt <= 0 (denominator guard).
        FCO can be negative -- the ratio is still meaningful (negative =
        cash-burning company cannot service debt from operations).
    """
    fco = operating_cf_at(company, date)
    if fco is None:
        return None
    debt = debt_at(company, date)
    if debt is None or debt <= 0:
        return None
    return fco / debt


def cash_flow_to_debt_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Cash Flow to Debt time series -- union of operating_cf + debt period dates."""
    fco_periods_list = operating_cf_periods(company)
    debt_periods_list = debt_periods(company)

    all_dates = set()
    for periods in [fco_periods_list, debt_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_fco = None
        for fp in reversed(fco_periods_list):
            if fp["date"] <= date:
                ttm_fco = fp["ttm_fco"]
                break
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break
        cfd = None
        if (ttm_fco is not None
            and debt is not None and debt > 0):
            cfd = ttm_fco / debt
        result.append({
            "date": date,
            "cash_flow_to_debt": cfd,
            "ttm_fco": ttm_fco,
            "debt": debt,
        })
    return result


register_metric(MetricSpec(
    name="cash_flow_to_debt",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="FCO/Dívida",
    ratio_key="cash_flow_to_debt",
    ratio_fn=cash_flow_to_debt_at,
    history_fn=cash_flow_to_debt_history,
    engines=["operating_cf", "debt"],
    category="leverage",
    aliases=["fco_divida", "cfd", "fluxo_caixa_divida"],
))
