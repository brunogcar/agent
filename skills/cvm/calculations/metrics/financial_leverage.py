"""metrics/financial_leverage.py -- Alavancagem Financeira (Assets / Equity) leverage ratio.

Financial Leverage = total_assets / pl
                   = Ativo Total / Patrimônio Líquido

Measures the degree to which the firm uses creditor financing (debt +
payables) relative to shareholder equity. A multiplier of N means every R$1
of equity supports R$N of total assets. Fundamental ratio (no price, no
shares). Composes total_assets + pl engines.

Equivalent interpretations:
  - Ativo / PL = 1 + (Passivo / PL) → identity from Ativo = Passivo + PL
  - Ativo / PL = 1 / equity_ratio (where equity_ratio = PL / Ativo)
  - Ativo / PL × ROA = ROE (DuPont decomposition)

Interpretation:
  - Leverage < 1.5: conservative (low creditor financing)
  - Leverage 1.5-3: moderate
  - Leverage > 3: high leverage (risky)
  - Leverage > 5: very high leverage (potential distress — common in banks
                  and utilities, where it may be normal)

Usage:
    from skills.cvm.calculations.metrics.financial_leverage import financial_leverage_at
    f = financial_leverage_at("PETR4", "2024-06-30")  # -> 2.1
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpa.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations.engines.bpp.pl import pl_at, pl_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def financial_leverage_at(company: str, date: str) -> float | None:
    """Financial Leverage = Ativo Total / PL."""
    total_assets = total_assets_at(company, date)
    if total_assets is None or total_assets <= 0:
        return None
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None
    return total_assets / pl


def financial_leverage_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Financial Leverage time series — union of total_assets + pl period dates."""
    ta_periods_list = total_assets_periods(company)
    pl_periods_list = pl_periods(company)

    all_dates = set()
    for periods in [ta_periods_list, pl_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        total_assets = None
        for tap in reversed(ta_periods_list):
            if tap["date"] <= date:
                total_assets = tap["total_assets"]
                break
        pl = None
        for pp in reversed(pl_periods_list):
            if pp["date"] <= date:
                pl = pp["pl"]
                break
        financial_leverage = None
        if (total_assets is not None and total_assets > 0
            and pl is not None and pl > 0):
            financial_leverage = total_assets / pl
        result.append({
            "date": date,
            "financial_leverage": financial_leverage,
            "total_assets": total_assets,
            "pl": pl,
        })
    return result


register_metric(MetricSpec(
    name="financial_leverage",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Alavancagem Financeira",
    ratio_key="financial_leverage",
    ratio_fn=financial_leverage_at,
    history_fn=financial_leverage_history,
    engines=["total_assets", "pl"],
    category="leverage",
    aliases=["alavancagem", "alavancagem_financeira", "ativo_pl", "grau_alavancagem"],
))
