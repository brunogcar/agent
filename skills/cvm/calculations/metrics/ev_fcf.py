"""metrics/ev_fcf.py -- EV/FCF (Enterprise Value to Free Cash Flow) metric.

EV/FCF = Enterprise Value / Free Cash Flow

Where:
  EV (Enterprise Value) = market_cap + debt - cash
    - market_cap = price × shares
    - debt = total debt (BPP 2.01.04 + 2.02.01)
    - cash = cash and equivalents (BPA 1.01.01)
  FCF = FCO + FCI
    - FCO = TTM Fluxo de Caixa Operacional   (DFC 6.01, typically POSITIVE)
    - FCI = TTM Fluxo de Caixa de Investimento (DFC 6.02, typically NEGATIVE)
    - FCF = FCO + FCI (FCO minus capex/acquisitions, since FCI < 0)

This is a VALUATION ratio, but unlike P/FCF it does NOT produce a per-share
intermediate value -- the ratio is the final output (EV divided by FCF).
It is therefore registered as a Type 2 fundamental ratio (per_share_*=None)
following the same pattern as ev_ebitda's ratio half but without the
per-share sibling.

Mirrors metrics/p_fcf.py's alignment-guard logic: FCO and FCI are resolved
via their *_periods() functions (not *_at()), and the resolved period-end
dates are compared. If they don't match (e.g., one engine has a data gap
at a quarter the other doesn't), the function returns None instead of
summing two different reporting periods.

Engines composed: price + shares + debt + cash + operating_cf + investing_cf

Interpretation:
  - EV/FCF < 10:  cheap (strong free cash flow relative to enterprise value)
  - EV/FCF 10-20: fair
  - EV/FCF 20-30: expensive
  - EV/FCF > 30:  very expensive (or capital-intensive business with weak FCF)
  - EV/FCF = None when FCF <= 0 or EV <= 0 (ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.ev_fcf import ev_fcf_at, ev_fcf_history
    r = ev_fcf_at("PETR4", "2024-06-30")    # -> 6.2 (EV/FCF ratio)
    h = ev_fcf_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at, investing_cf_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def _resolve_fcf(company: str, date: str) -> tuple[float | None, str | None]:
    """Resolve TTM FCO + TTM FCI at the most recent period-end <= date.

    [v1.22 fix] Was calling operating_cf_periods() + investing_cf_periods()
    which fetch ALL DFC data and compute TTM for every period — took 95-133s.
    Now calls operating_cf_at() + investing_cf_at() which are cached + only
    fetch the most recent period <= date. Expected: 95s → <0.01s.

    FCO and FCI come from the SAME DFC statement, so alignment is guaranteed
    (both resolve to the same period-end). The old alignment guard was
    defensive but unnecessary for same-statement engines.
    """
    fco_val = operating_cf_at(company, date)
    fci_val = investing_cf_at(company, date)

    if fco_val is None or fci_val is None:
        return None, None

    # FCO + FCI = Free Cash Flow (both are TTM, same period)
    return fco_val + fci_val, date


# -- Ratio: EV/FCF = (price × shares + debt - cash) / (FCO + FCI) -------------

def ev_fcf_at(company: str, date: str) -> float | None:
    """Compute EV/FCF at a specific date.

    EV/FCF = (price × shares + debt - cash) / (FCO + FCI)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EV/FCF ratio as float, or None if:
        - any component is missing
        - FCO and FCI resolve to different period-end dates (alignment guard)
        - FCF <= 0 (negative free cash flow -- ratio meaningless)
        - EV <= 0 (negative enterprise value -- ratio meaningless)
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

    fcf, _resolved_date = _resolve_fcf(company, date)
    if fcf is None or fcf <= 0:
        return None  # Misaligned periods OR non-positive FCF -> meaningless

    market_cap = price * shares
    ev = market_cap + debt - cash
    if ev <= 0:
        return None  # Negative enterprise value -> ratio meaningless

    return ev / fcf


# -- History: daily series with EV/FCF ----------------------------------------

def ev_fcf_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EV/FCF time series for a date range.

    Step-function optimization:
    - price:        daily
    - shares:       annual (step)
    - debt:         quarterly (step)
    - cash:         quarterly (step)
    - operating_cf: quarterly (step, TTM)
    - investing_cf: quarterly (step, TTM)

    For each daily price, find the most recent shares, debt, cash, TTM FCO,
    TTM FCI (with alignment guard -- only sum if both resolve to same date),
    then compute EV = price × shares + debt - cash, EV/FCF = EV / FCF.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ev_fcf", "ev", "fcf", "ttm_fco",
                 "ttm_fci", "debt", "cash", "shares"} sorted oldest-first.
        Entries with None (missing data, misaligned FCO/FCI, negative FCF/EV)
        are included with ev_fcf=None so charts show gaps.
    """
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    shares_periods_list = shares_periods(company)
    debt_periods_list = debt_periods(company)
    cash_periods_list = cash_periods(company)
    fco_periods_list = operating_cf_periods(company)
    fci_periods_list = investing_cf_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        shares = None
        for sp in reversed(shares_periods_list):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break

        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break

        # Resolve FCO + FCI (alignment guard inside)
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

        # Alignment guard
        fcf = None
        if (ttm_fco is not None and ttm_fci is not None
            and fco_resolved_date == fci_resolved_date):
            fcf = ttm_fco + ttm_fci

        ev = None
        ev_fcf = None
        if (fcf is not None and fcf > 0
            and price is not None and price > 0
            and shares is not None and shares > 0
            and debt is not None
            and cash is not None):
            ev = price * shares + debt - cash
            if ev > 0:
                ev_fcf = ev / fcf

        result.append({
            "date": date,
            "price": price,
            "ev_fcf": ev_fcf,
            "ev": ev,
            "fcf": fcf,
            "ttm_fco": ttm_fco,
            "ttm_fci": ttm_fci,
            "debt": debt,
            "cash": cash,
            "shares": shares,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="ev_fcf",
    per_share_label=None,        # Type 2 fundamental ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="EV/FCF",
    ratio_key="ev_fcf",
    ratio_fn=ev_fcf_at,
    history_fn=ev_fcf_history,
    engines=["price", "shares", "debt", "cash", "operating_cf", "investing_cf"],
    category="valuation",
    aliases=["ev_fcf", "evfcf"],
))
