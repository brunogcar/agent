"""metrics/dl_ebit.py -- DL/EBIT (Net Debt / EBIT) fundamental ratio.

DL/EBIT = (Debt - Cash) / EBIT
        = Dívida Líquida / EBIT

Measures how many years of EBIT it would take to pay off net debt.
Fundamental ratio (no price, no shares). Composes debt + cash + ebit.

Mirrors metrics/net_debt_ebitda.py with one simplification: uses EBIT
directly instead of EBITDA (EBIT + D&A). This means no `da` engine is
needed — one fewer engine dependency.

DL/EBIT is stricter than DL/EBITDA because EBIT < EBITDA (D&A is
subtracted). A company with DL/EBITDA of 3x might have DL/EBIT of 4-5x
if it has high depreciation. This metric is preferred by analysts who
treat D&A as a real cost (capex replacement).

Engines composed: debt + cash + ebit

Interpretation:
  - DL/EBIT < 2: healthy (low leverage)
  - DL/EBIT 2-4: moderate
  - DL/EBIT > 5: high leverage (potential distress)
  - DL/EBIT < 0: net cash (negative net debt -- company has more cash than debt)

Usage:
    from skills.cvm.calculations.metrics.dl_ebit import dl_ebit_at
    d = dl_ebit_at("PETR4", "2024-06-30")  # -> 2.1
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def dl_ebit_at(company: str, date: str) -> float | None:
    """Net Debt / EBIT = (Debt - Cash) / EBIT.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        DL/EBIT ratio as float, or None if any component is missing or
        EBIT <= 0 (negative EBIT -- ratio meaningless).
    """
    debt = debt_at(company, date)
    if debt is None:
        return None
    cash = cash_at(company, date)
    if cash is None:
        return None
    ebit = ebit_at(company, date)
    if ebit is None:
        return None
    if ebit <= 0:
        return None  # Negative EBIT -- ratio meaningless
    net_debt = debt - cash
    return net_debt / ebit


def dl_ebit_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """DL/EBIT time series — union of debt + cash + ebit period dates."""
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    ebit_periods_list = ebit_periods(company)

    all_dates = set()
    for periods in [debt_periods_list, cash_periods_list, ebit_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        # Find most recent debt <= date
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break

        # Find most recent cash <= date
        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break

        # Find most recent EBIT <= date
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break

        dl_ebit = None
        if (debt is not None and cash is not None
            and ttm_ebit is not None and ttm_ebit > 0):
            dl_ebit = (debt - cash) / ttm_ebit

        result.append({
            "date": date,
            "dl_ebit": dl_ebit,
            "debt": debt,
            "cash": cash,
            "ebit": ttm_ebit,
        })
    return result


register_metric(MetricSpec(
    name="dl_ebit",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="DL/EBIT",
    ratio_key="dl_ebit",
    ratio_fn=dl_ebit_at,
    history_fn=dl_ebit_history,
    engines=["debt", "cash", "ebit"],
    category="leverage",
    aliases=["net_debt_ebit", "divida_liquida_ebit", "dl/ebit"],
))
