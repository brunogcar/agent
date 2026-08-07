"""metrics/magic_number.py -- Magic Number (Greenblatt-inspired) fundamental metric.

Magic Number = EV / EBITDA × ROIC

Combines cheapness (EV/EBITDA) with quality (ROIC). A low EV/EBITDA with
high ROIC = good company at a good price. Inspired by Joel Greenblatt's
"magic formula" — ranks companies by the combination of cheap + good.

This is a FUNDAMENTAL RATIO — it composes 6 engines (price + shares +
debt + cash + ebit + da for EV/EBITDA) transitively through ev_ebitda +
roic metrics, but we compute it directly from engines to avoid double
engine calls (F7 cache handles this if called within scope).

Engines composed: price + shares + debt + cash + ebit + da + tax + pl

Interpretation:
  - Magic Number < 5: excellent (cheap + high quality)
  - Magic Number 5-15: good
  - Magic Number 15-30: fair
  - Magic Number > 30: expensive or low quality
  - Magic Number = None when EBITDA <= 0 or ROIC <= 0

Usage:
    from skills.cvm.calculations.metrics.magic_number import magic_number_at
    m = magic_number_at("PETR4", "2024-06-30")  # -> 8.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations.engines.bpp.debt import debt_at
from skills.cvm.calculations.engines.bpa.cash import cash_at
from skills.cvm.calculations.engines.dre.ebit import ebit_at
from skills.cvm.calculations.engines.dfc.da import da_at
from skills.cvm.calculations.engines.bpp.pl import pl_at
from skills.cvm.calculations.engines.dre.tax import tax_at
from skills.cvm.calculations._registry import MetricSpec, register_metric


def magic_number_at(company: str, date: str) -> float | None:
    """Magic Number = EV / EBITDA × ROIC.

    EV/EBITDA = (price × shares + debt - cash) / (EBIT + D&A)
    ROIC = NOPAT / Invested Capital

    NOPAT formula: EBIT - max(0, tax_expense) (simplified — same as roic.py).
    This differs from the textbook NOPAT = EBIT × (1 - tax/EBT) which
    requires EBT. The simplified version is used to avoid requiring the
    EBT engine. Document this limitation when comparing Magic Number's
    ROIC component with standalone ROIC.

    Returns None if EBITDA <= 0 or ROIC <= 0 or any component missing.
    """
    # EV/EBITDA components
    price = price_at(company, date)
    if price is None or price <= 0:
        return None
    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None
    debt = debt_at(company, date)
    if debt is None:
        return None
    cash = cash_at(company, date)
    if cash is None:
        return None
    ebit = ebit_at(company, date)
    if ebit is None:
        return None
    da = da_at(company, date)
    if da is None:
        return None

    ebitda = ebit + da
    if ebitda <= 0:
        return None

    ev = price * shares + debt - cash
    ev_ebitda = ev / ebitda

    # ROIC components
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None
    tax = tax_at(company, date)
    if tax is None:
        return None

    invested_capital = pl + debt
    if invested_capital <= 0:
        return None

    nopat = ebit - max(0, tax)
    roic = nopat / invested_capital
    if roic <= 0:
        return None

    return ev_ebitda * roic


def magic_number_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Magic Number time series — union of all 8 engine period dates."""
    from skills.cvm.calculations.engines.price import price_series
    from skills.cvm.calculations.engines.shares import shares_periods
    from skills.cvm.calculations.engines.bpp.debt import debt_periods
    from skills.cvm.calculations.engines.bpa.cash import cash_periods
    from skills.cvm.calculations.engines.dre.ebit import ebit_periods
    from skills.cvm.calculations.engines.dfc.da import da_periods
    from skills.cvm.calculations.engines.bpp.pl import pl_periods
    from skills.cvm.calculations.engines.dre.tax import tax_periods

    all_dates = set()
    for periods in [shares_periods(company), debt_periods(company),
                    cash_periods(company), ebit_periods(company),
                    da_periods(company), pl_periods(company),
                    tax_periods(company)]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])

    prices = price_series(company, date_from, date_to)
    price_dates = {p["date"]: p["close"] for p in prices}
    all_dates.update(price_dates.keys())

    result = []
    for d in sorted(all_dates):
        mn = magic_number_at(company, d)
        result.append({"date": d, "magic_number": mn})
    return result


register_metric(MetricSpec(
    name="magic_number",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Magic Number",
    ratio_key="magic_number",
    ratio_fn=magic_number_at,
    history_fn=magic_number_history,
    engines=["price", "shares", "debt", "cash", "ebit", "da", "pl", "tax"],
    category="valuation",
    aliases=["magic", "magic_formula"],
))
