"""metrics/cash_ratio.py -- Cash Ratio (liquidity) fundamental ratio metric.

Cash Ratio = Cash / Current Liabilities
           = Caixa / Passivo Circulante

Measures the most conservative liquidity -- the ability to pay short-term
obligations using ONLY cash and equivalents (no inventory, no receivables).
Fundamental ratio (no price, no shares). Composes cash + current_liabilities
engines.

Interpretation:
  - Cash Ratio > 1.0: very strong liquidity (could pay all current
    liabilities from cash alone)
  - Cash Ratio 0.2-0.5: healthy (typical for non-financial companies)
  - Cash Ratio < 0.1: potential liquidity stress
  - Cash Ratio < 0: would mean negative cash -- rare, treat as None
  - Cash Ratio = None when current_liabilities <= 0 (rare for non-financial)

Engines composed: cash + current_liabilities

Usage:
    from skills.cvm.calculations.metrics.cash_ratio import cash_ratio_at
    c = cash_ratio_at("PETR4", "2024-06-30")  # -> 0.32 (32%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.bpp.current_liabilities import (
    current_liabilities_at,
    current_liabilities_periods,
)
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def cash_ratio_at(company: str, date: str) -> float | None:
    """Cash Ratio = Cash / Current Liabilities.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Cash Ratio as a fraction (0.32 = 32%), or None if either component
        is missing or current_liabilities <= 0 (denominator guard).
        Cash can be zero (returns 0.0 -- valid: company has no cash).
    """
    cash = cash_at(company, date)
    if cash is None:
        return None
    current_liab = current_liabilities_at(company, date)
    if current_liab is None or current_liab <= 0:
        return None
    return cash / current_liab


def cash_ratio_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Cash Ratio time series -- union of cash + current_liabilities dates."""
    cash_periods_list = cash_periods(company)
    cl_periods_list = current_liabilities_periods(company)

    all_dates = set()
    for periods in [cash_periods_list, cl_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        cash = None
        cash = lookup_lte(cash_periods_list, date, "cash")
        current_liab = None
        current_liab = lookup_lte(cl_periods_list, date, "current_liabilities")
        cash_ratio = None
        if (cash is not None
            and current_liab is not None and current_liab > 0):
            cash_ratio = cash / current_liab
        result.append({
            "date": date,
            "cash_ratio": cash_ratio,
            "cash": cash,
            "current_liabilities": current_liab,
        })
    return result


register_metric(MetricSpec(
    name="cash_ratio",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Índice de Caixa",
    ratio_key="cash_ratio",
    ratio_fn=cash_ratio_at,
    history_fn=cash_ratio_history,
    engines=["cash", "current_liabilities"],
    category="liquidity",
    aliases=["razao_caixa", "cash_ratio", "cr_caixa"],
))
