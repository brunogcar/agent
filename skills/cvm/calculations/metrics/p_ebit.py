"""metrics/p_ebit.py -- EBIT/Ação (EBIT per share) + P/EBIT (Price-to-EBIT) metric.

EBIT/Ação = EBIT / shares          (per-share value, from ebit + shares engines)
P/EBIT    = price / (EBIT / shares) (price ratio, adds price engine)
         = price × shares / EBIT

This metric produces BOTH:
  - EBIT/Ação (per-share value): useful on its own
  - P/EBIT (price ratio):        tells you if the stock is cheap vs history

Mirrors metrics/lpa.py with two substitutions:
  - earnings engine → ebit engine (TTM EBIT instead of TTM earnings)
  - LPA / P/L labels → EBIT/Ação / P/EBIT labels

Engines composed: price + ebit + shares

Interpretation:
  - P/EBIT < 6:  cheap
  - P/EBIT 6-10: fair
  - P/EBIT 10-15: expensive
  - P/EBIT > 15: very expensive
  - P/EBIT = None when EBIT <= 0 (negative EBIT -- ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.p_ebit import ebit_ps_at, p_ebit_at, p_ebit_history
    e = ebit_ps_at("PETR4", "2024-06-30")   # -> 18.50 (EBIT per share)
    r = p_ebit_at("PETR4", "2024-06-30")    # -> 3.2 (P/EBIT ratio)
    h = p_ebit_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: EBIT/Ação = EBIT / shares ───────────────────────────────

def ebit_ps_at(company: str, date: str) -> float | None:
    """Compute EBIT/Ação (EBIT per share) at a specific date.

    EBIT/Ação = TTM EBIT / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        EBIT per share in BRL, or None if EBIT or shares are missing/zero.
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return ebit / shares


# ── Price ratio: P/EBIT = price / (EBIT / shares) ────────────────────────────

def p_ebit_at(company: str, date: str) -> float | None:
    """Compute P/EBIT (Price-to-EBIT) at a specific date.

    P/EBIT = price / (EBIT / shares) = price × shares / EBIT

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/EBIT ratio as float, or None if any component is missing or
        EBIT <= 0 (negative EBIT -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    ebit_ps = ebit_ps_at(company, date)
    if ebit_ps is None or ebit_ps <= 0:
        return None  # Negative/zero EBIT → P/EBIT is meaningless

    return price / ebit_ps


# ── History: daily series with EBIT/Ação + P/EBIT ────────────────────────────

def p_ebit_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily EBIT/Ação + P/EBIT time series for a date range.

    Optimized: TTM EBIT change only when new ITR/DFP is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all TTM EBIT periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent TTM EBIT + shares
    4. Compute EBIT/Ação = TTM EBIT / shares, then P/EBIT = price / (EBIT/Ação)

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ebit_ps", "p_ebit", "ttm_ebit", "shares"}
        sorted oldest-first. Entries with None EBIT/Ação/P_EBIT (negative
        EBIT, missing data) are included with ebit_ps=None, p_ebit=None so
        charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM EBIT periods (quarterly step function)
    ebit_periods_list = ebit_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM EBIT <= date
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute EBIT/Ação = TTM EBIT / shares
        ebit_ps = None
        if ttm_ebit is not None and ttm_ebit > 0 and shares is not None and shares > 0:
            ebit_ps = ttm_ebit / shares

        # Compute P/EBIT = price / (EBIT/Ação)
        p_ebit = None
        if ebit_ps is not None and ebit_ps > 0 and price > 0:
            p_ebit = price / ebit_ps

        result.append({
            "date": date,
            "price": price,
            "ebit_ps": ebit_ps,
            "p_ebit": p_ebit,
            "ttm_ebit": ttm_ebit,
            "shares": shares,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="p_ebit",
    per_share_label="EBIT/Ação",
    per_share_key="ebit_ps",
    per_share_fn=ebit_ps_at,
    ratio_label="P/EBIT",
    ratio_key="p_ebit",
    ratio_fn=p_ebit_at,
    history_fn=p_ebit_history,
    engines=["price", "shares", "ebit"],
    category="valuation",
    aliases=["p_ebit", "pebit", "preco_ebit"],
))
