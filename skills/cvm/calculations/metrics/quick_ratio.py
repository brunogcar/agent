"""metrics/quick_ratio.py -- Quick Ratio (Acid Test) fundamental ratio metric.

Quick Ratio = (Cash + Receivables) / Current Liabilities
            = (Caixa + Contas a Receber) / Passivo Circulante

Also known as the Acid Test. A stricter liquidity measure than the current
ratio -- excludes inventory (which may be hard to liquidate) from the
numerator. Cash + receivables are the most liquid current assets.

Fundamental ratio (no price, no shares). Composes cash + receivables +
current_liabilities engines.

Interpretation:
  - Quick Ratio > 1.0: healthy (can cover short-term obligations without
    selling inventory)
  - Quick Ratio 0.5-1.0: tight liquidity
  - Quick Ratio < 0.5: high risk of short-term default
  - Quick Ratio < 0: meaningful only if current_liabilities > 0 (negative
    numerator means receivables < 0, which is rare and likely a restatement)

Guards:
  - current_liabilities must be > 0 (denominator).
  - Cash and receivables can each be 0 -- the ratio is still computed with
    what is available.
  - If either cash or receivables is None (data missing), return None --
    the metric is incomplete and reporting a partial value would mislead
    users.

Engines composed: cash + receivables + current_liabilities.

Usage:
    from skills.cvm.calculations.metrics.quick_ratio import quick_ratio_at
    q = quick_ratio_at("PETR4", "2024-06-30")  # -> 1.1
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.bpa.receivables import receivables_at, receivables_periods
from skills.cvm.calculations.engines.bpp.current_liabilities import (
    current_liabilities_at, current_liabilities_periods,
)
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def quick_ratio_at(company: str, date: str) -> float | None:
    """Quick Ratio = (Cash + Receivables) / Current Liabilities.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Quick ratio as float, or None if current_liabilities is missing/
        non-positive, or if either cash or receivables is missing (data
        incomplete). Cash and receivables may each be 0 (valid).
    """
    cash = cash_at(company, date)
    if cash is None:
        return None
    receivables = receivables_at(company, date)
    if receivables is None:
        return None
    current_liab = current_liabilities_at(company, date)
    if current_liab is None or current_liab <= 0:
        return None
    return (cash + receivables) / current_liab


def quick_ratio_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Quick Ratio time series -- union of cash + receivables + current_liabilities dates.

    Each entry contains the quick_ratio plus the underlying snapshot values.
    Entries with None ratio (missing data) are included so charts show gaps.
    """
    cash_periods_list = cash_periods(company)
    recv_periods_list = receivables_periods(company)
    cl_periods_list = current_liabilities_periods(company)

    all_dates = set()
    for periods in [cash_periods_list, recv_periods_list, cl_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        cash = None
        cash = lookup_lte(cash_periods_list, date, "cash")
        receivables = None
        receivables = lookup_lte(recv_periods_list, date, "receivables")
        current_liab = None
        current_liab = lookup_lte(cl_periods_list, date, "current_liabilities")
        quick_ratio = None
        if (cash is not None and receivables is not None
                and current_liab is not None and current_liab > 0):
            quick_ratio = (cash + receivables) / current_liab
        result.append({
            "date": date,
            "quick_ratio": quick_ratio,
            "cash": cash,
            "receivables": receivables,
            "current_liabilities": current_liab,
        })
    return result


register_metric(MetricSpec(
    name="quick_ratio",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Liquidez Seca",
    ratio_key="quick_ratio",
    ratio_fn=quick_ratio_at,
    history_fn=quick_ratio_history,
    engines=["cash", "receivables", "current_liabilities"],
    category="liquidity",
    aliases=["liquidez_seca", "acid_test", "qr"],
))
