"""metrics/effective_tax_rate.py -- Effective Tax Rate fundamental ratio metric.

Effective Tax Rate = tax_expense / EBT (Earnings Before Tax)

Where:
  tax_expense = abs(tax) when tax < 0 (DRE 3.08 stores tax as negative expense)
  EBT = Earnings Before Tax (DRE 3.07, with description-search fallback)

Clamped to [0, 1.0] (0% to 100%). Values > 100% indicate data errors or
special tax situations (deferred tax adjustments, tax credits).

Interpretation:
  - < 15%:  low (tax incentives, deferred tax benefits, or losses in prior periods)
  - 15-25%: normal range for Brazilian companies (IRPJ 15% + CSLL 9% = 24% base rate)
  - 25-34%: high (additional 10% IRPJ surtax on profit > R$240k/year)
  - > 34%:  very high (special situations, deferred tax reversals)
  - None when EBT <= 0 (can't compute tax rate on losses)

Engines composed: tax + ebt

Usage:
    from skills.cvm.calculations.metrics.effective_tax_rate import effective_tax_rate_at
    r = effective_tax_rate_at("PETR4", "2024-06-30")    # -> 0.24 (24%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.tax import tax_at, tax_periods
from skills.cvm.calculations.engines.ebt import ebt_at, ebt_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def effective_tax_rate_at(company: str, date: str) -> float | None:
    """Compute Effective Tax Rate at a specific date.

    effective_tax_rate = tax_expense / EBT

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Effective tax rate as a fraction (0.24 = 24%), clamped to [0, 1.0],
        or None if EBT is None or <= 0 (can't compute on losses).
    """
    ebt = ebt_at(company, date)
    if ebt is None or ebt <= 0:
        return None

    tax = tax_at(company, date)
    if tax is None or tax >= 0:
        # No tax expense (tax credit or zero) → effective rate = 0
        return 0.0

    tax_expense = -tax  # Convert negative DRE value to positive expense
    rate = tax_expense / ebt

    # Clamp to [0, 1.0] — values > 100% are data anomalies
    return min(max(rate, 0.0), 1.0)


def effective_tax_rate_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Effective Tax Rate time series — union of tax + ebt period dates."""
    tax_periods_list = tax_periods(company)
    ebt_periods_list = ebt_periods(company)

    all_dates = set()
    for periods in [tax_periods_list, ebt_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_tax = None
        for tp in reversed(tax_periods_list):
            if tp["date"] <= date:
                ttm_tax = tp["ttm_tax"]
                break
        ttm_ebt = None
        for ep in reversed(ebt_periods_list):
            if ep["date"] <= date:
                ttm_ebt = ep["ttm_ebt"]
                break

        etr = None
        if (ttm_ebt is not None and ttm_ebt > 0
            and ttm_tax is not None and ttm_tax < 0):
            rate = (-ttm_tax) / ttm_ebt
            etr = min(max(rate, 0.0), 1.0)
        elif ttm_ebt is not None and ttm_ebt > 0:
            etr = 0.0  # No tax expense

        result.append({
            "date": date,
            "effective_tax_rate": etr,
            "ttm_tax": ttm_tax,
            "ttm_ebt": ttm_ebt,
        })
    return result


register_metric(MetricSpec(
    name="effective_tax_rate",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Taxa Efetiva",
    ratio_key="effective_tax_rate",
    ratio_fn=effective_tax_rate_at,
    history_fn=effective_tax_rate_history,
    engines=["tax", "ebt"],
    aliases=["taxa_efetiva", "etr", "tax_rate", "effective_tax", "aliquota_efetiva"],
))
