"""metrics/fcl.py -- FCL (Fluxo de Caixa Livre / Free Cash Flow) metric.

FCL = FCO - |CapEx|

Where:
  FCO   = Operating Cash Flow (DFC 6.01, TTM) — cash from operations
  CapEx = Capital Expenditure (DFC, TTM, by description search) — typically
          NEGATIVE (cash outflow for asset purchases), so we take |CapEx|
          to subtract it as a positive outflow from FCO.

FCL represents the "true" free cash flow — cash left after maintaining the
business (capex). This is the cash available to return to shareholders
(dividends, buybacks) or reduce debt.

NOTE: This is DIFFERENT from the `fcf` key in ratios_dict which = FCO + FCI
(FCI is investing CF, which includes more than just capex — acquisitions,
asset sales, etc.). FCL is a stricter measure: only subtracts capex.

Interpretation:
  - FCL > 0: company generates cash after capex (healthy)
  - FCL < 0: company spends more on capex than operations generate (growth
             phase or distressed)
  - FCL / shares = FCF per share (available for dividends/buybacks)

Engines composed: operating_cf + capex

Usage:
    from skills.cvm.calculations.metrics.fcl import fcl_at
    f = fcl_at("PETR4", "2024-06-30")  # -> 50e9 (50B BRL, TTM)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.dfc.capex import capex_at, capex_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def fcl_at(company: str, date: str) -> float | None:
    """Compute FCL (Free Cash Flow = FCO - |CapEx|) at a specific date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        FCL in BRL (TTM), or None if FCO or CapEx is unavailable.
    """
    fco = operating_cf_at(company, date)
    if fco is None:
        return None

    capex = capex_at(company, date)
    if capex is None:
        return None

    # CapEx is typically NEGATIVE (cash outflow). |CapEx| = positive outflow.
    # FCL = FCO - |CapEx| = FCO + CapEx (since CapEx is negative).
    # But to be safe (some filers report capex as positive), use: FCO - abs(CapEx)
    return fco - abs(capex)


def fcl_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """FCL time series (quarterly step function).

    FCL changes when FCO (quarterly) or CapEx (quarterly) changes.
    """
    fco_periods = operating_cf_periods(company)
    capex_p = capex_periods(company)

    all_dates = set()
    for p in fco_periods:
        if date_from <= p["date"] <= date_to:
            all_dates.add(p["date"])
    for p in capex_p:
        if date_from <= p["date"] <= date_to:
            all_dates.add(p["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result = []
    for d in sorted_dates:
        fco = operating_cf_at(company, d)
        capex = capex_at(company, d)
        fcl = None
        if fco is not None and capex is not None:
            fcl = fco - abs(capex)
        result.append({"date": d, "fcl": fcl, "fco": fco, "capex": capex})

    return result


register_metric(MetricSpec(
    name="fcl",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="FCL (Fluxo de Caixa Livre)",
    ratio_key="fcl",
    ratio_fn=fcl_at,
    history_fn=fcl_history,
    engines=["operating_cf", "capex"],
    category="cash_flow",
    aliases=["free_cash_flow", "fluxo_caixa_livre", "fcf_capex"],
    tooltip="FCL = FCO - |CapEx|. Fluxo de Caixa Livre = Operacional menos investimentos em ativos. Caixa disponível para dividendos/buybacks.",
))
