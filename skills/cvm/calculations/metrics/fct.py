"""metrics/fct.py -- FCT (Fluxo de Caixa Total / Total Cash Flow) metric.

FCT = FCO + FCI + FCF (financing)

Where:
  FCO = Operating Cash Flow (DFC 6.01, TTM)
  FCI = Investing Cash Flow (DFC 6.02, TTM)
  FCF = Financing Cash Flow (DFC 6.03, TTM) — NOT "Free Cash Flow"!
        (CVM naming: FCF = "Fluxo de Caixa de Financiamento")

FCT represents the NET change in cash over the period — the sum of all
three cash flow sections. By accounting identity:
  FCT = ΔCaixa (change in cash balance from start to end of period)

This is useful for:
  - Verifying DFC data quality (FCT should match ΔCaixa from BPA)
  - Seeing the total cash generation/consumption profile
  - Comparing vs FCL (Free Cash Flow) to understand financing effects

Interpretation:
  - FCT > 0: company increased its cash position over the period
  - FCT < 0: company consumed cash (distributed via dividends, buybacks,
             debt repayment, or capex exceeding operations)
  - FCT ≈ 0: stable cash position (operations fund all activities)

NOTE: "FCF" in the DFC context means "Fluxo de Caixa de Financiamento"
(Financing Cash Flow), NOT "Free Cash Flow". The existing `fcf` key in
ratios_dict = FCO + FCI (a rough free cash flow proxy). This metric uses
the DFC's financing CF (DFC 6.03).

Engines composed: operating_cf + investing_cf + financing_cf

Usage:
    from skills.cvm.calculations.metrics.fct import fct_at
    t = fct_at("PETR4", "2024-06-30")  # -> -10e9 (-10B BRL, TTM)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at, investing_cf_periods
from skills.cvm.calculations.engines.dfc.financing_cf import financing_cf_at, financing_cf_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def fct_at(company: str, date: str) -> float | None:
    """Compute FCT (Total Cash Flow = FCO + FCI + FCF) at a specific date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        FCT in BRL (TTM), or None if any of the three components is None.
    """
    fco = operating_cf_at(company, date)
    fci = investing_cf_at(company, date)
    fcf = financing_cf_at(company, date)

    if fco is None or fci is None or fcf is None:
        return None

    return fco + fci + fcf


def fct_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """FCT time series (quarterly step function)."""
    fco_periods = operating_cf_periods(company)
    fci_periods = investing_cf_periods(company)
    fcf_periods = financing_cf_periods(company)

    all_dates = set()
    for p in fco_periods:
        if date_from <= p["date"] <= date_to:
            all_dates.add(p["date"])
    for p in fci_periods:
        if date_from <= p["date"] <= date_to:
            all_dates.add(p["date"])
    for p in fcf_periods:
        if date_from <= p["date"] <= date_to:
            all_dates.add(p["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result = []
    for d in sorted_dates:
        fco = operating_cf_at(company, d)
        fci = investing_cf_at(company, d)
        fcf = financing_cf_at(company, d)
        fct = None
        if fco is not None and fci is not None and fcf is not None:
            fct = fco + fci + fcf
        result.append({"date": d, "fct": fct, "fco": fco, "fci": fci, "fcf": fcf})

    return result


register_metric(MetricSpec(
    name="fct",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="FCT (Fluxo de Caixa Total)",
    ratio_key="fct",
    ratio_fn=fct_at,
    history_fn=fct_history,
    engines=["operating_cf", "investing_cf", "financing_cf"],
    category="cash_flow",
    aliases=["total_cash_flow", "fluxo_caixa_total", "net_cash_flow"],
    tooltip="FCT = FCO + FCI + FCF. Fluxo de Caixa Total = Operacional + Investimento + Financiamento. Variação líquida de caixa.",
))
