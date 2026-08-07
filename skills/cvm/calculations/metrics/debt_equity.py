"""metrics/debt_equity.py -- Debt/Equity fundamental ratio metric.

Debt/Equity = Total Debt / Patrimônio Líquido
            = Dívida / PL

Measures financial leverage. Fundamental ratio (no price, no shares).
Composes debt + pl engines.

Interpretation:
  - D/E < 0.5: conservative (low leverage)
  - D/E 0.5-1.5: moderate
  - D/E > 2.0: high leverage (risky)
  - D/E > 5.0: very high leverage (potential distress)

Usage:
    from skills.cvm.calculations.metrics.debt_equity import debt_equity_at
    d = debt_equity_at("PETR4", "2024-06-30")  # -> 0.85
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpp.pl import pl_at, pl_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def debt_equity_at(company: str, date: str) -> float | None:
    """Debt/Equity = Total Debt / PL."""
    debt = debt_at(company, date)
    if debt is None or debt < 0:
        return None
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None
    return debt / pl


def debt_equity_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Debt/Equity time series — union of debt + pl period dates."""
    debt_periods_list = debt_periods(company)
    pl_periods_list = pl_periods(company)

    all_dates = set()
    for periods in [debt_periods_list, pl_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break
        pl = None
        for pp in reversed(pl_periods_list):
            if pp["date"] <= date:
                pl = pp["pl"]
                break
        debt_equity = None
        if (debt is not None and debt >= 0
            and pl is not None and pl > 0):
            debt_equity = debt / pl
        result.append({"date": date, "debt_equity": debt_equity, "debt": debt, "pl": pl})
    return result


register_metric(MetricSpec(
    name="debt_equity",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Dívida/PL",
    ratio_key="debt_equity",
    ratio_fn=debt_equity_at,
    history_fn=debt_equity_history,
    engines=["debt", "pl"],
    category="leverage",
    aliases=["de", "divida_pl", "divida_patrimonio"],
))
