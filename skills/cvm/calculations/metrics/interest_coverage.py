"""metrics/interest_coverage.py -- Interest Coverage Ratio fundamental metric.

Interest Coverage Ratio = EBIT / |Financial Result (net)|
                        = EBIT / |Resultado Financeiro Líquido|

Measures the company's ability to service its interest obligations from
operating earnings.

APPROXIMATION CAVEAT
--------------------
The `financial_result` engine (DRE codigo 3.06) returns the NET financial
result = financial income - financial expenses. For a textbook Interest
Coverage Ratio, the denominator should be GROSS interest expense (DRE
codigo 3.06.02 "Despesas Financeiras"). That gross figure requires a
separate engine that is on the ROADMAP but not yet implemented.

This metric uses abs(financial_result) as an APPROXIMATION of interest
expense. The approximation is tight when financial income is small
relative to financial expense (typical for non-financial companies with
significant debt); it is loose when the company has large offsetting
financial income (e.g., a retailer with a big cash position earning
interest that partially offsets interest expense).

SIGN CONVENTION
---------------
- financial_result < 0 (net expense): the standard case. Denominator =
  abs(financial_result). Ratio = EBIT / abs(financial_result).
- financial_result >= 0 (net income or zero): NO interest expense to
  cover on a net basis -- the metric is meaningless. Return None.

Guards:
  - EBIT must be > 0 (negative EBIT means the company can't even cover
    operations, let alone interest).
  - financial_result must be < 0 (net expense). Otherwise return None.
  - If either is None (data missing), return None.

Engines composed: ebit + financial_result.

Interpretation (when financial_result < 0):
  - ICR > 5.0:    comfortable interest coverage
  - ICR 2.0-5.0:  adequate
  - ICR 1.0-2.0:  tight -- watch for earnings deterioration
  - ICR < 1.0:    EBIT does not cover interest expense -- distress risk
  - ICR < 0:      not possible (EBIT > 0 + |financial_result| > 0)

Usage:
    from skills.cvm.calculations.metrics.interest_coverage import interest_coverage_at
    icr = interest_coverage_at("PETR4", "2024-06-30")  # -> 6.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dre.financial_result import (
    financial_result_at, financial_result_periods,
)
from skills.cvm.calculations._registry import MetricSpec, register_metric


def interest_coverage_at(company: str, date: str) -> float | None:
    """Interest Coverage Ratio = EBIT / |Financial Result (net)|.

    Uses the NET financial result (financial income - financial expense)
    from the financial_result engine as an APPROXIMATION of interest
    expense. See module docstring for the full caveat.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Interest Coverage Ratio as float, or None if:
          - EBIT is None or <= 0 (can't cover anything)
          - financial_result is None
          - financial_result >= 0 (net income -- no expense to cover)
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit <= 0:
        return None
    financial_result = financial_result_at(company, date)
    if financial_result is None:
        return None
    if financial_result >= 0:
        # Net financial income (or zero) -- no interest expense to cover.
        return None
    return ebit / abs(financial_result)


def interest_coverage_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Interest Coverage time series -- union of ebit + financial_result dates.

    Both engines are TTM flows, so dates are ITR/DFP filing period-end dates
    (quarterly step function). Each entry contains the ICR plus the
    underlying TTM values. Entries with None ICR (missing data or
    non-meaningful case) are included so charts show gaps.
    """
    ebit_periods_list = ebit_periods(company)
    fr_periods_list = financial_result_periods(company)

    all_dates = set()
    for periods in [ebit_periods_list, fr_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break
        ttm_fr = None
        for fp in reversed(fr_periods_list):
            if fp["date"] <= date:
                ttm_fr = fp["ttm_financial_result"]
                break
        icr = None
        if (ttm_ebit is not None and ttm_ebit > 0
                and ttm_fr is not None and ttm_fr < 0):
            icr = ttm_ebit / abs(ttm_fr)
        result.append({
            "date": date,
            "interest_coverage": icr,
            "ttm_ebit": ttm_ebit,
            "ttm_financial_result": ttm_fr,
        })
    return result


register_metric(MetricSpec(
    name="interest_coverage",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Cobertura de Juros",
    ratio_key="interest_coverage",
    ratio_fn=interest_coverage_at,
    history_fn=interest_coverage_history,
    engines=["ebit", "financial_result"],
    category="leverage",
    aliases=[
        "cobertura_juros", "ic", "icr",
        "cobertura_despesa_financeira",
    ],
))
