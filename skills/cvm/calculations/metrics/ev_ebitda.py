"""metrics/ev_ebitda.py -- EV/EBITDA (Enterprise Value to EBITDA) metric.

EV/EBITDA = Enterprise Value / EBITDA

Where:
  EV (Enterprise Value) = market_cap + debt - cash
    - market_cap = price × shares
    - debt = total debt (BPP 2.01.04 + 2.02.01)
    - cash = cash and equivalents (BPA 1.01.01)
  EBITDA = EBIT + D&A (Depreciation & Amortization)
    - EBIT = TTM EBIT (DRE 3.05)
    - D&A = TTM Depreciação e Amortização (DFC, description search)

This metric produces BOTH:
  - EBITDA per share (per-share value): useful on its own
  - EV/EBITDA (price ratio): tells you if the stock is cheap vs enterprise value

Engines composed: price + shares + debt + cash + ebit + da (6 engines -- the
most complex metric so far)

EV/EBITDA is NOT a simple price / per_share_value ratio. It's:
  EV/EBITDA = (price × shares + debt - cash) / EBITDA
            = (price + (debt - cash) / shares) / (EBITDA / shares)
            = (price + net_debt_per_share) / ebitda_per_share

So the ratio includes net debt per share as an adjustment to price. This is
why EV/EBITDA is more comprehensive than P/L -- it accounts for capital
structure (debt and cash).

Interpretation:
  - EV/EBITDA < 6: cheap
  - EV/EBITDA 6-10: fair
  - EV/EBITDA 10-15: expensive
  - EV/EBITDA > 15: very expensive (or high growth expectations)
  - EV/EBITDA < 0: meaningless (negative EBITDA -- company losing money
    at the operating level before D&A)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.ev_ebitda import ebitda_ps_at, ev_ebitda_at, ev_ebitda_history
    e = ebitda_ps_at("PETR4", "2024-06-30")   # -> 12.50 (EBITDA per share)
    r = ev_ebitda_at("PETR4", "2024-06-30")    # -> 4.2 (EV/EBITDA ratio)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations.engines.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.da import da_at, da_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# -- Per-share value: EBITDA per share = (EBIT + D&A) / shares ----------------

def ebitda_ps_at(company: str, date: str) -> float | None:
    """Compute EBITDA per share at a specific date.

    EBITDA per share = (TTM EBIT + TTM D&A) / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EBITDA per share in BRL, or None if any component is missing.
    """
    ebit = ebit_at(company, date)
    if ebit is None:
        return None

    da = da_at(company, date)
    if da is None:
        return None

    ebitda = ebit + da
    if ebitda <= 0:
        return None  # Negative EBITDA -- per-share value meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return ebitda / shares


# -- Price ratio: EV/EBITDA = (market_cap + debt - cash) / EBITDA -------------

def ev_ebitda_at(company: str, date: str) -> float | None:
    """Compute EV/EBITDA at a specific date.

    EV/EBITDA = (price × shares + debt - cash) / (EBIT + D&A)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EV/EBITDA ratio as float, or None if any component is missing or
        EBITDA <= 0 (negative EBITDA -- ratio meaningless).
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

    da = da_at(company, date)
    if da is None:
        return None

    ebitda = ebit + da
    if ebitda <= 0:
        return None  # Negative EBITDA -- EV/EBITDA meaningless

    market_cap = price * shares
    ev = market_cap + debt - cash

    return ev / ebitda


# -- History: daily series with EBITDA/share + EV/EBITDA ----------------------

def ev_ebitda_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EBITDA/share + EV/EBITDA time series for a date range.

    Step-function optimization:
    - price: daily
    - shares: annual (step)
    - debt: quarterly (step)
    - cash: quarterly (step)
    - ebit: quarterly (step)
    - da: quarterly (step)

    For each daily price, find the most recent shares, debt, cash, ebit, da,
    then compute EBITDA/share and EV/EBITDA.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ebitda_ps", "ev_ebitda", "ebit", "da",
                 "debt", "cash", "shares"} sorted oldest-first.
        Entries with None (missing data, negative EBITDA) are included with
        ebitda_ps=None, ev_ebitda=None so charts show gaps.
    """
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    shares_periods_list = shares_periods(company)
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    ebit_periods_list = ebit_periods(company)
    da_periods_list = da_periods(company)

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

        # Find most recent D&A <= date
        ttm_da = None
        for dap in reversed(da_periods_list):
            if dap["date"] <= date:
                ttm_da = dap["ttm_da"]
                break

        # Compute EBITDA = EBIT + D&A
        ebitda = None
        if ttm_ebit is not None and ttm_da is not None:
            ebitda = ttm_ebit + ttm_da

        # Compute EBITDA per share
        ebitda_ps = None
        if ebitda is not None and ebitda > 0 and shares is not None and shares > 0:
            ebitda_ps = ebitda / shares

        # Compute EV/EBITDA = (price × shares + debt - cash) / EBITDA
        ev_ebitda = None
        if (ebitda is not None and ebitda > 0
            and price is not None and price > 0
            and shares is not None and shares > 0
            and debt is not None
            and cash is not None):
            market_cap = price * shares
            ev = market_cap + debt - cash
            ev_ebitda = ev / ebitda

        result.append({
            "date": date,
            "price": price,
            "ebitda_ps": ebitda_ps,
            "ev_ebitda": ev_ebitda,
            "ebit": ttm_ebit,
            "da": ttm_da,
            "debt": debt,
            "cash": cash,
            "shares": shares,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="ev_ebitda",
    per_share_label="EBITDA/Ação",
    per_share_key="ebitda_ps",
    per_share_fn=ebitda_ps_at,
    ratio_label="EV/EBITDA",
    ratio_key="ev_ebitda",
    ratio_fn=ev_ebitda_at,
    history_fn=ev_ebitda_history,
    engines=["price", "shares", "debt", "cash", "ebit", "da"],
    aliases=["ev_ebit", "evebitda", "eva_ebitda"],
))
