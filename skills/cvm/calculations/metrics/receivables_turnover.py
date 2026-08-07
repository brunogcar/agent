"""metrics/receivables_turnover.py -- Receivables Turnover fundamental ratio metric.

Receivables Turnover = Revenue / Receivables
                     = Receita Líquida / Contas a Receber

Measures how efficiently a company collects cash from its customers.
Higher turnover means receivables are converted to cash quickly
(efficient collections, tight credit policy); lower turnover may
indicate loose credit terms, slow-paying customers, or collection
issues.

PERIOD MISMATCH CAVEAT
----------------------
The numerator (TTM revenue) is a 12-month flow ending at the most
recent ITR/DFP period on or before `date`. The denominator (receivables)
is a point-in-time snapshot at the most recent BPA on or before `date`.
In practice both align to the same period-end date for filers with both
BPA and DRE data, but if a filer files only annual statements, the
receivables snapshot could lag the TTM flow by up to a year. The metric
does NOT enforce date alignment -- callers should be aware of this.

Engines composed: revenue + receivables.

Interpretation (industry-dependent):
  - High turnover (e.g., 12+/year): fast collection cycle (cash sales
    dominant, or tight credit terms)
  - Low turnover (< 4/year): slow collection, capital tied up in
    receivables, possible credit-risk build-up
  - Related metric: Days Sales Outstanding (DSO) = 365 / turnover

Guards:
  - receivables must be > 0 (denominator).
  - revenue must be > 0 (negative or zero revenue makes the ratio
    meaningless).
  - If either is None, return None.

Usage:
    from skills.cvm.calculations.metrics.receivables_turnover import receivables_turnover_at
    rto = receivables_turnover_at("PETR4", "2024-06-30")  # -> 7.0
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.bpa.receivables import receivables_at, receivables_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def receivables_turnover_at(company: str, date: str) -> float | None:
    """Receivables Turnover = Revenue / Receivables.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Receivables Turnover ratio as float, or None if either revenue
        or receivables is missing, or receivables <= 0, or revenue <= 0.
    """
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    receivables = receivables_at(company, date)
    if receivables is None or receivables <= 0:
        return None
    return revenue / receivables


def receivables_turnover_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Receivables Turnover time series -- union of revenue + receivables dates.

    Revenue dates are quarterly TTM period-end dates; receivables dates
    are quarterly BPA snapshot dates. Both typically align. Each entry
    contains the ratio plus underlying TTM revenue + receivables snapshot.
    Entries with None ratio are included so charts show gaps.
    """
    rev_periods_list = revenue_periods(company)
    recv_periods_list = receivables_periods(company)

    all_dates = set()
    for periods in [rev_periods_list, recv_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_rev = None
        for rp in reversed(rev_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break
        receivables = None
        for rp in reversed(recv_periods_list):
            if rp["date"] <= date:
                receivables = rp["receivables"]
                break
        rto = None
        if (ttm_rev is not None and ttm_rev > 0
                and receivables is not None and receivables > 0):
            rto = ttm_rev / receivables
        result.append({
            "date": date,
            "receivables_turnover": rto,
            "ttm_rev": ttm_rev,
            "receivables": receivables,
        })
    return result


register_metric(MetricSpec(
    name="receivables_turnover",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Giro de Contas a Receber",
    ratio_key="receivables_turnover",
    ratio_fn=receivables_turnover_at,
    history_fn=receivables_turnover_history,
    engines=["revenue", "receivables"],
    category="efficiency",
    aliases=["giro_contas_receber", "rto", "receivables_turn"],
))
