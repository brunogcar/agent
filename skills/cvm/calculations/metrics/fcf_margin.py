"""metrics/fcf_margin.py -- Free Cash Flow Margin fundamental ratio metric.

FCF Margin = (FCO + FCI) / Revenue
           = (Fluxo de Caixa Operacional + Fluxo de Caixa de Investimento)
             / Receita Líquida

Measures how much free cash flow a company generates per unit of revenue.
Unlike OCF Margin (which doesn't account for capex), FCF Margin subtracts
investing cash flows (which include capex, acquisitions, etc.) -- so it
reflects the cash actually available to return to shareholders (dividends,
buybacks, debt paydown) after maintaining the business.

Where:
  FCO = TTM Fluxo de Caixa Operacional   (DFC 6.01, typically POSITIVE)
  FCI = TTM Fluxo de Caixa de Investimento (DFC 6.02, typically NEGATIVE)
  FCF = FCO + FCI                         (FCO minus capex/acquisitions)

Mirrors metrics/p_fcf.py's alignment-guard logic: FCO and FCI are resolved
via their *_periods() functions (not *_at()), and the resolved period-end
dates are compared. If they don't match (e.g., one engine has a data gap
at a quarter the other doesn't), the function returns None instead of
summing two different reporting periods.

Engines composed: operating_cf + investing_cf + revenue

Interpretation:
  - FCF Margin > 15%: excellent (high free cash flow conversion)
  - FCF Margin 5-15%: good
  - FCF Margin < 0%: company is burning free cash flow (FCO insufficient
    to cover capex/investments -- red flag for capital-intensive businesses)
  - FCF Margin = None when FCF <= 0 (negative free cash flow -- margin
    meaningless; we choose to surface as None rather than report a negative
    margin which can be confusing) or revenue <= 0

Usage:
    from skills.cvm.calculations.metrics.fcf_margin import fcf_margin_at
    m = fcf_margin_at("PETR4", "2024-06-30")  # -> 0.12 (12%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.operating_cf import operating_cf_periods
from skills.cvm.calculations.engines.investing_cf import investing_cf_periods
from skills.cvm.calculations.engines.revenue import revenue_at, revenue_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def _resolve_fcf(company: str, date: str) -> tuple[float | None, str | None]:
    """Resolve TTM FCO + TTM FCI at the most recent period-end <= date.

    Returns (fcf_value, resolved_period_date). If FCO and FCI resolve to
    different dates, returns (None, None) so callers can short-circuit.
    Mirrors the alignment-guard logic in metrics/p_fcf.py::fcf_ps_at.
    """
    fco_periods_list = operating_cf_periods(company)
    fco_date: str | None = None
    fco_val: float | None = None
    for fp in reversed(fco_periods_list):
        if fp["date"] <= date:
            fco_date = fp["date"]
            fco_val = fp["ttm_fco"]
            break

    fci_periods_list = investing_cf_periods(company)
    fci_date: str | None = None
    fci_val: float | None = None
    for ip in reversed(fci_periods_list):
        if ip["date"] <= date:
            fci_date = ip["date"]
            fci_val = ip["ttm_fci"]
            break

    if fco_val is None or fci_val is None:
        return None, None

    if fco_date != fci_date:
        return None, None

    return fco_val + fci_val, fco_date


def fcf_margin_at(company: str, date: str) -> float | None:
    """FCF Margin = (FCO + FCI) / Revenue.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        FCF Margin as a fraction (0.12 = 12%), or None if:
        - FCO or FCI is missing
        - FCO and FCI resolve to different period-end dates (alignment guard)
        - FCF <= 0 (negative free cash flow -- margin meaningless)
        - Revenue is missing or <= 0 (denominator guard)
    """
    fcf, _resolved_date = _resolve_fcf(company, date)
    if fcf is None or fcf <= 0:
        return None  # Misaligned periods OR non-positive FCF -> meaningless

    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None

    return fcf / revenue


def fcf_margin_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """FCF Margin time series -- union of operating_cf + investing_cf + revenue
    period dates.
    """
    fco_periods_list = operating_cf_periods(company)
    fci_periods_list = investing_cf_periods(company)
    rev_periods_list = revenue_periods(company)

    all_dates = set()
    for periods in [fco_periods_list, fci_periods_list, rev_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_fco = None
        fco_resolved_date = None
        for fp in reversed(fco_periods_list):
            if fp["date"] <= date:
                ttm_fco = fp["ttm_fco"]
                fco_resolved_date = fp["date"]
                break

        ttm_fci = None
        fci_resolved_date = None
        for ip in reversed(fci_periods_list):
            if ip["date"] <= date:
                ttm_fci = ip["ttm_fci"]
                fci_resolved_date = ip["date"]
                break

        ttm_rev = None
        for rp in reversed(rev_periods_list):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break

        # Alignment guard
        fcf = None
        if (ttm_fco is not None and ttm_fci is not None
            and fco_resolved_date == fci_resolved_date):
            fcf = ttm_fco + ttm_fci

        fcf_margin = None
        if (fcf is not None and fcf > 0
            and ttm_rev is not None and ttm_rev > 0):
            fcf_margin = fcf / ttm_rev

        result.append({
            "date": date,
            "fcf_margin": fcf_margin,
            "fcf": fcf,
            "ttm_fco": ttm_fco,
            "ttm_fci": ttm_fci,
            "ttm_rev": ttm_rev,
        })
    return result


register_metric(MetricSpec(
    name="fcf_margin",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Margem FCF",
    ratio_key="fcf_margin",
    ratio_fn=fcf_margin_at,
    history_fn=fcf_margin_history,
    engines=["operating_cf", "investing_cf", "revenue"],
    aliases=["margem_fcf", "fcf_margem"],
))
