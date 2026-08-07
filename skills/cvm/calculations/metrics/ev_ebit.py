"""metrics/ev_ebit.py -- EV/EBIT (Enterprise Value to EBIT) metric.

EV/EBIT = Enterprise Value / EBIT

Where:
  EV (Enterprise Value) = market_cap + debt - cash
    - market_cap = price × shares
    - debt = total debt (BPP 2.01.04 + 2.02.01)
    - cash = cash and equivalents (BPA 1.01.01)
  EBIT = TTM EBIT (DRE 3.05)

This metric produces BOTH:
  - EBIT per share (per-share value): useful on its own
  - EV/EBIT (price ratio): tells you if the stock is cheap vs enterprise value

Mirrors metrics/ev_ebitda.py with one simplification: uses EBIT directly
instead of EBITDA (EBIT + D&A). This means no `da` engine is needed —
one fewer engine dependency.

EV/EBIT is useful for comparing companies with different D&A policies
(companies with high capital intensity have high D&A, making EBITDA
flatter than EBIT). Some analysts prefer EV/EBIT because it accounts
for D&A as a real cost (capex replacement).

Engines composed: price + shares + debt + cash + ebit (5 engines)

Interpretation:
  - EV/EBIT < 6: cheap
  - EV/EBIT 6-10: fair
  - EV/EBIT 10-15: expensive
  - EV/EBIT > 15: very expensive (or high growth expectations)
  - EV/EBIT = None when EBIT <= 0 (negative EBIT -- ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.ev_ebit import ebit_ps_at, ev_ebit_at, ev_ebit_history
    e = ebit_ps_at("PETR4", "2024-06-30")   # -> 18.50 (EBIT per share)
    r = ev_ebit_at("PETR4", "2024-06-30")    # -> 3.5 (EV/EBIT ratio)
    h = ev_ebit_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Per-share value: EBIT per share = EBIT / shares --------------------------

def ebit_ps_at(company: str, date: str) -> float | None:
    """Compute EBIT per share at a specific date.

    EBIT per share = TTM EBIT / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EBIT per share in BRL, or None if any component is missing.
    """
    ebit = ebit_at(company, date)
    if ebit is None:
        return None

    if ebit <= 0:
        return None  # Negative EBIT -- per-share value meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return ebit / shares


# -- Price ratio: EV/EBIT = (market_cap + debt - cash) / EBIT -----------------

def ev_ebit_at(company: str, date: str) -> float | None:
    """Compute EV/EBIT at a specific date.

    EV/EBIT = (price × shares + debt - cash) / EBIT

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EV/EBIT ratio as float, or None if any component is missing or
        EBIT <= 0 (negative EBIT -- ratio meaningless).
    """
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

    if ebit <= 0:
        return None  # Negative EBIT -- EV/EBIT meaningless

    market_cap = price * shares
    ev = market_cap + debt - cash

    return ev / ebit


# -- History: daily series with EBIT/share + EV/EBIT --------------------------

def ev_ebit_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EBIT/share + EV/EBIT time series for a date range.

    Step-function optimization:
    - price: daily
    - shares: annual (step)
    - debt: quarterly (step)
    - cash: quarterly (step)
    - ebit: quarterly (step)

    For each daily price, find the most recent shares, debt, cash, ebit,
    then compute EBIT/share and EV/EBIT.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ebit_ps", "ev_ebit", "ebit",
                 "debt", "cash", "shares"} sorted oldest-first.
    """
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    shares_periods_list = shares_periods(company)
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    ebit_periods_list = ebit_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent shares <= date
        shares = None
        for sp in reversed(shares_periods_list):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Find most recent debt <= date
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break

        # Find most recent cash <= date
        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break

        # Find most recent EBIT <= date
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break

        # Compute EBIT per share
        ebit_ps = None
        if ttm_ebit is not None and ttm_ebit > 0 and shares is not None and shares > 0:
            ebit_ps = ttm_ebit / shares

        # Compute EV/EBIT = (price × shares + debt - cash) / EBIT
        ev_ebit = None
        if (ttm_ebit is not None and ttm_ebit > 0
            and price is not None and price > 0
            and shares is not None and shares > 0
            and debt is not None
            and cash is not None):
            market_cap = price * shares
            ev = market_cap + debt - cash
            ev_ebit = ev / ttm_ebit

        result.append({
            "date": date,
            "price": price,
            "ebit_ps": ebit_ps,
            "ev_ebit": ev_ebit,
            "ebit": ttm_ebit,
            "debt": debt,
            "cash": cash,
            "shares": shares,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="ev_ebit",
    per_share_label="EBIT/Ação",
    per_share_key="ebit_ps",
    per_share_fn=ebit_ps_at,
    ratio_label="EV/EBIT",
    ratio_key="ev_ebit",
    ratio_fn=ev_ebit_at,
    history_fn=ev_ebit_history,
    engines=["price", "shares", "debt", "cash", "ebit"],
    category="valuation",
    aliases=["evebit", "ev/ebit"],
))
