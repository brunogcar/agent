"""metrics/gross_debt_equity.py -- Dívida Bruta / Patrimônio Líquido (Gross Debt / Equity) leverage ratio.

Gross Debt / Equity = debt / pl
                     = Dívida Bruta / Patrimônio Líquido

Measures financial leverage. Fundamental ratio (no price, no shares).
Composes debt + pl engines.

NOTE
----
The `debt` engine returns Empréstimos e Financiamentos (BPP codes 2.01.04 +
2.02.01), which is gross debt (loans + financing) -- NOT net debt (which
would subtract cash). So this metric is the canonical "Gross Debt / Equity"
leverage ratio from the private spreadsheet.

The existing `debt_equity` metric computes the same formula. We keep
`gross_debt_equity` as a separate canonical name with Portuguese aliases
("divida_bruta_pl", "divida_bruta_patrimonio", "db_pl") so that callers
querying for "dívida bruta / PL" explicitly resolve to this entry, and so
that the spreadsheet's "Dív. Bruta / PL" line maps cleanly. Both metrics
return identical numeric values for the same (company, date).

Interpretation:
  - D/E < 0.5: conservative (low leverage)
  - D/E 0.5-1.5: moderate
  - D/E > 2.0: high leverage (risky)
  - D/E > 5.0: very high leverage (potential distress)

Usage:
    from skills.cvm.calculations.metrics.gross_debt_equity import gross_debt_equity_at
    d = gross_debt_equity_at("PETR4", "2024-06-30")  # -> 0.85
"""
from __future__ import annotations

from skills.cvm.calculations.engines.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def gross_debt_equity_at(company: str, date: str) -> float | None:
    """Gross Debt / Equity = total debt / PL."""
    debt = debt_at(company, date)
    if debt is None or debt < 0:
        return None
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None
    return debt / pl


def gross_debt_equity_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Gross Debt / Equity time series — union of debt + pl period dates."""
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
        gross_debt_equity = None
        if (debt is not None and debt >= 0
            and pl is not None and pl > 0):
            gross_debt_equity = debt / pl
        result.append({
            "date": date,
            "gross_debt_equity": gross_debt_equity,
            "debt": debt,
            "pl": pl,
        })
    return result


register_metric(MetricSpec(
    name="gross_debt_equity",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Dív. Bruta / PL",
    ratio_key="gross_debt_equity",
    ratio_fn=gross_debt_equity_at,
    history_fn=gross_debt_equity_history,
    engines=["debt", "pl"],
    category="leverage",
    aliases=["divida_bruta_pl", "divida_bruta_patrimonio", "db_pl", "gross_de"],
))
