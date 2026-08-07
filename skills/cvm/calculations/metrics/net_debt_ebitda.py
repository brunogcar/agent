"""metrics/net_debt_ebitda.py -- Net Debt / EBITDA (DL/EBITDA) fundamental ratio.

Net Debt / EBITDA = (Debt - Cash) / (EBIT + D&A)
                  = Dívida Líquida / EBITDA

Measures how many years of EBITDA it would take to pay off net debt.
Fundamental ratio (no price, no shares). Composes debt + cash + ebit + da.

Interpretation:
  - DL/EBITDA < 2: healthy (low leverage)
  - DL/EBITDA 2-4: moderate
  - DL/EBITDA > 5: high leverage (potential distress)
  - DL/EBITDA < 0: net cash (negative net debt -- company has more cash than debt)

Usage:
    from skills.cvm.calculations.metrics.net_debt_ebitda import net_debt_ebitda_at
    d = net_debt_ebitda_at("PETR4", "2024-06-30")  # -> 1.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dfc.da import da_at, da_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def net_debt_ebitda_at(company: str, date: str) -> float | None:
    """Net Debt / EBITDA = (Debt - Cash) / (EBIT + D&A)."""
    debt = debt_at(company, date)
    if debt is None:
        return None
    cash = cash_at(company, date)
    if cash is None:
        return None
    ebit = ebit_at(company, date)
    if ebit is None:
        return None
    da = da_at(company, date)
    if da is None:
        return None
    ebitda = ebit + da
    if ebitda <= 0:
        return None  # Negative EBITDA -- ratio meaningless
    net_debt = debt - cash
    return net_debt / ebitda


def net_debt_ebitda_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Net Debt / EBITDA time series — union of 4 engine period dates."""
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    ebit_periods_list = ebit_periods(company)
    da_periods_list = da_periods(company)

    all_dates = set()
    for periods in [debt_periods_list, cash_periods_list, ebit_periods_list, da_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break
        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break
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
        ebitda = None
        if ttm_ebit is not None and ttm_da is not None:
            ebitda = ttm_ebit + ttm_da
        net_debt_ebitda = None
        if (debt is not None and cash is not None
            and ebitda is not None and ebitda > 0):
            net_debt_ebitda = (debt - cash) / ebitda
        result.append({"date": date, "net_debt_ebitda": net_debt_ebitda,
                        "debt": debt, "cash": cash, "ttm_ebit": ttm_ebit, "ttm_da": ttm_da})
    return result


register_metric(MetricSpec(
    name="net_debt_ebitda",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="DL/EBITDA",
    ratio_key="net_debt_ebitda",
    ratio_fn=net_debt_ebitda_at,
    history_fn=net_debt_ebitda_history,
    engines=["debt", "cash", "ebit", "da"],
    category="leverage",
    aliases=["nde", "dl_ebitda", "divida_liquida_ebitda", "net_debt_to_ebitda"],
))
