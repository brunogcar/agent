"""metrics/roi.py -- ROI (Return on Investment) metric.

ROI = NOPAT / Invested Capital (at book value)

Where:
  NOPAT            = EBIT × (1 - effective_tax_rate)
  Invested Capital = PL + Debt - Cash (book values)

This is similar to ROIC but uses invested-capital-at-book (the same formula
as the existing ROIC metric, but ROI is registered separately so consumers
can reference it by the `roi` alias). The key difference from ROIC is that
ROI uses the EFFECTIVE tax rate from DRE (not a flat 34%), making it more
accurate than the approximate ROIC that used 34% in early versions.

NOTE: The existing `roic` metric already uses the effective tax rate (since
the calculations v2.0 refactor). So ROI and ROIC will produce IDENTICAL
values. ROI exists as a separate metric for naming clarity — some analysts
prefer "ROI" (Return on Investment) vs "ROIC" (Return on Invested Capital),
and the alias ensures both names work.

Engines composed: ebit, pl, debt, cash, effective_tax_rate

Usage:
    from skills.cvm.calculations.metrics.roi import roi_at
    r = roi_at("PETR4", "2024-06-30")  # -> 0.15 (fraction, = 15%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.ebit import ebit_at
from skills.cvm.calculations.engines.bpp.pl import pl_at
from skills.cvm.calculations.engines.bpp.debt import debt_at
from skills.cvm.calculations.engines.bpa.cash import cash_at
from skills.cvm.calculations.metrics.effective_tax_rate import effective_tax_rate_at
from skills.cvm.calculations._registry import MetricSpec, register_metric


def roi_at(company: str, date: str) -> float | None:
    """Compute ROI (Return on Investment) at a specific date.

    ROI = NOPAT / Invested Capital
      NOPAT            = EBIT × (1 - effective_tax_rate)
      Invested Capital = PL + Debt - Cash

    Returns None when:
        - EBIT is None or <= 0 (operating losses — ROI meaningless)
        - PL is None or <= 0 (negative equity)
        - Debt is None (no debt data)
        - Invested Capital <= 0

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROI as a fraction (0.15 = 15%), or None.
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit <= 0:
        return None

    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None

    debt = debt_at(company, date)
    if debt is None:
        return None

    cash = cash_at(company, date)
    cash_val = cash if cash is not None else 0.0

    invested = pl + debt - cash_val
    if invested <= 0:
        return None

    tax = effective_tax_rate_at(company, date)
    tax_rate = tax if tax is not None else 0.34  # Default 34% (IRPJ+CSLL)

    nopat = ebit * (1.0 - tax_rate)
    return nopat / invested


def roi_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """ROI history not supported — depends on quarterly EBIT + PL + debt + tax.

    Computing for 5Y of daily dates would be expensive. Use roic_history()
    instead (same formula, different alias).
    """
    return []


register_metric(MetricSpec(
    name="roi",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="ROI",
    ratio_key="roi",
    ratio_fn=roi_at,
    history_fn=roi_history,
    engines=["ebit", "pl", "debt", "cash", "effective_tax_rate"],
    category="profitability",
    aliases=["return_on_investment"],
    tooltip="ROI = NOPAT / Capital Investido. Retorno sobre o capital aportado (PL + Dívida - Caixa).",
))
