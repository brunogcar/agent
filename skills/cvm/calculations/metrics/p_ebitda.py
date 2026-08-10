"""metrics/p_ebitda.py -- EBITDA/Ação (EBITDA per share) + P/EBITDA (Price-to-EBITDA) metric.

EBITDA/Ação = (EBIT + D&A) / shares   (per-share value, from ebit + da + shares engines)
P/EBITDA    = price / EBITDA/Ação     (price ratio, adds price engine)

EBITDA is NOT a standalone engine — it's computed as EBIT + D&A (Depreciação
e Amortização). See metrics/ebitda_margin.py for the same composition pattern.

This metric produces BOTH:
  - EBITDA/Ação (per-share value): EBITDA per share, useful on its own
  - P/EBITDA (price ratio):        tells you if the stock is cheap vs history

Mirrors metrics/p_ebit.py with one extension: adds the `da` engine so the
operating profit (EBIT) is upgraded to EBITDA (EBIT + D&A).

Engines composed: price + ebit + da + shares

Interpretation:
  - P/EBITDA < 5:  cheap
  - P/EBITDA 5-10: fair
  - P/EBITDA 10-15: expensive
  - P/EBITDA > 15: very expensive
  - P/EBITDA = None when EBITDA <= 0 (negative EBITDA -- ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.p_ebitda import ebitda_ps_at, p_ebitda_at, p_ebitda_history
    e = ebitda_ps_at("PETR4", "2024-06-30")  # -> 22.80 (EBITDA per share)
    r = p_ebitda_at("PETR4", "2024-06-30")   # -> 1.65 (P/EBITDA ratio)
    h = p_ebitda_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dfc.da import da_at, da_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# ── Per-share value: EBITDA/Ação = (EBIT + D&A) / shares ─────────────────────

def ebitda_ps_at(company: str, date: str) -> float | None:
    """Compute EBITDA/Ação (EBITDA per share) at a specific date.

    EBITDA/Ação = (TTM EBIT + TTM D&A) / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EBITDA per share in BRL, or None if EBIT/D&A/shares are missing/zero.
    """
    ebit = ebit_at(company, date)
    if ebit is None:
        return None
    da = da_at(company, date)
    if da is None:
        return None
    ebitda = ebit + da
    if ebitda == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return ebitda / shares


# ── Price ratio: P/EBITDA = price / EBITDA/Ação ──────────────────────────────

def p_ebitda_at(company: str, date: str) -> float | None:
    """Compute P/EBITDA (Price-to-EBITDA) at a specific date.

    P/EBITDA = price / EBITDA/Ação = price / ((EBIT + D&A) / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/EBITDA ratio as float, or None if any component is missing or
        EBITDA/Ação <= 0 (zero/negative EBITDA -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    ebitda_ps = ebitda_ps_at(company, date)
    if ebitda_ps is None or ebitda_ps <= 0:
        return None  # Negative/zero EBITDA → P/EBITDA is meaningless

    return price / ebitda_ps


# ── History: daily series with EBITDA/Ação + P/EBITDA ────────────────────────

def p_ebitda_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EBITDA/Ação + P/EBITDA time series for a date range.

    Optimized: TTM EBIT and TTM D&A change only when new ITR/DFP is filed
    (quarterly). Shares change annually. Price changes daily. So we:
    1. Get all TTM EBIT periods (step function — ~4 per year)
    2. Get all TTM D&A periods (step function — ~4 per year)
    3. Get all shares periods (step function — ~1 per year)
    4. For each daily price, find the most recent TTM EBIT + TTM D&A + shares
    5. Compute EBITDA = EBIT + D&A, then EBITDA/Ação = EBITDA / shares,
       then P/EBITDA = price / EBITDA/Ação

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ebit_ps", "p_ebitda", "ttm_ebit",
                 "ttm_da", "shares"} sorted oldest-first. Entries with None
        EBITDA/Ação/P_EBITDA (negative EBITDA, missing data) are included
        with ebit_ps=None, p_ebitda=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM EBIT periods (quarterly step function)
    ebit_periods_list = ebit_periods(company)

    # Get TTM D&A periods (quarterly step function)
    da_periods_list = da_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM EBIT <= date
        ttm_ebit = None
        ttm_ebit = lookup_lte(ebit_periods_list, date, "ttm_ebit")

        # Find most recent TTM D&A <= date
        ttm_da = None
        ttm_da = lookup_lte(da_periods_list, date, "ttm_da")

        # Find most recent shares <= date
        shares = None
        shares = lookup_lte(sh_periods, date, "shares")

        # Compute EBITDA = EBIT + D&A, then EBITDA/Ação = EBITDA / shares
        ebitda_ps = None
        if (ttm_ebit is not None and ttm_da is not None
            and shares is not None and shares > 0):
            ebitda = ttm_ebit + ttm_da
            if ebitda > 0:
                ebitda_ps = ebitda / shares

        # Compute P/EBITDA = price / EBITDA/Ação
        p_ebitda = None
        if ebitda_ps is not None and ebitda_ps > 0 and price > 0:
            p_ebitda = price / ebitda_ps

        result.append({
            "date": date,
            "price": price,
            "ebit_ps": ebitda_ps,
            "p_ebitda": p_ebitda,
            "ttm_ebit": ttm_ebit,
            "ttm_da": ttm_da,
            "shares": shares,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="p_ebitda",
    per_share_label="EBITDA/Ação",
    per_share_key="ebit_ps",
    per_share_fn=ebitda_ps_at,
    ratio_label="P/EBITDA",
    ratio_key="p_ebitda",
    ratio_fn=p_ebitda_at,
    history_fn=p_ebitda_history,
    engines=["price", "ebit", "da", "shares"],
    category="valuation",
    aliases=["p_ebitda", "pebitda", "p/ebitda", "preco_ebitda"],
))
