"""metrics/p_fco.py -- FCO/Ação (Operating CF per share) + P/FCO (Price-to-FCO) metric.

FCO/Ação = FCO / shares           (per-share value, from operating_cf + shares engines)
P/FCO    = price / (FCO / shares) (price ratio, adds price engine)
         = price × shares / FCO

This metric produces BOTH:
  - FCO/Ação (per-share value): useful on its own
  - P/FCO (price ratio):        tells you if the stock is cheap vs operating cash flow

Mirrors metrics/p_ebit.py with one substitution:
  - ebit engine → operating_cf engine (TTM FCO instead of TTM EBIT)

Engines composed: price + operating_cf + shares

Interpretation:
  - P/FCO < 6:  cheap (strong cash generation relative to price)
  - P/FCO 6-10: fair
  - P/FCO 10-15: expensive
  - P/FCO > 15: very expensive (or weak operating cash flow)
  - P/FCO = None when FCO <= 0 (negative operating cash flow -- ratio
    meaningless; company burning cash at the operating level)

P/FCO is more conservative than P/L because operating cash flow:
  - Excludes non-cash items (depreciation, amortization)
  - Excludes capital structure effects (interest expense)
  - Excludes tax effects (income tax)
  - Is harder to manipulate via accounting accruals

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.p_fco import fco_ps_at, p_fco_at, p_fco_history
    e = fco_ps_at("PETR4", "2024-06-30")   # -> 22.30 (FCO per share)
    r = p_fco_at("PETR4", "2024-06-30")    # -> 2.7 (P/FCO ratio)
    h = p_fco_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: FCO/Ação = FCO / shares ─────────────────────────────────

def fco_ps_at(company: str, date: str) -> float | None:
    """Compute FCO/Ação (Operating Cash Flow per share) at a specific date.

    FCO/Ação = TTM FCO / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        FCO per share in BRL, or None if FCO or shares are missing/zero.
    """
    fco = operating_cf_at(company, date)
    if fco is None or fco == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return fco / shares


# ── Price ratio: P/FCO = price / (FCO / shares) ──────────────────────────────

def p_fco_at(company: str, date: str) -> float | None:
    """Compute P/FCO (Price-to-Operating-Cash-Flow) at a specific date.

    P/FCO = price / (FCO / shares) = price × shares / FCO

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/FCO ratio as float, or None if any component is missing or
        FCO <= 0 (negative operating cash flow -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    fco_ps = fco_ps_at(company, date)
    if fco_ps is None or fco_ps <= 0:
        return None  # Negative/zero FCO → P/FCO is meaningless

    return price / fco_ps


# ── History: daily series with FCO/Ação + P/FCO ──────────────────────────────

def p_fco_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily FCO/Ação + P/FCO time series for a date range.

    Optimized: TTM FCO change only when new ITR/DFP is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all TTM FCO periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent TTM FCO + shares
    4. Compute FCO/Ação = TTM FCO / shares, then P/FCO = price / (FCO/Ação)

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "fco_ps", "p_fco", "ttm_fco", "shares"}
        sorted oldest-first. Entries with None FCO/Ação/P_FCO (negative
        FCO, missing data) are included with fco_ps=None, p_fco=None so
        charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM FCO periods (quarterly step function)
    fco_periods_list = operating_cf_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM FCO <= date
        ttm_fco = None
        for fp in reversed(fco_periods_list):
            if fp["date"] <= date:
                ttm_fco = fp["ttm_fco"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute FCO/Ação = TTM FCO / shares
        fco_ps = None
        if ttm_fco is not None and ttm_fco > 0 and shares is not None and shares > 0:
            fco_ps = ttm_fco / shares

        # Compute P/FCO = price / (FCO/Ação)
        p_fco = None
        if fco_ps is not None and fco_ps > 0 and price > 0:
            p_fco = price / fco_ps

        result.append({
            "date": date,
            "price": price,
            "fco_ps": fco_ps,
            "p_fco": p_fco,
            "ttm_fco": ttm_fco,
            "shares": shares,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="p_fco",
    per_share_label="FCO/Ação",
    per_share_key="fco_ps",
    per_share_fn=fco_ps_at,
    ratio_label="P/FCO",
    ratio_key="p_fco",
    ratio_fn=p_fco_at,
    history_fn=p_fco_history,
    engines=["price", "shares", "operating_cf"],
    aliases=["p_fco", "pfco", "preco_fco"],
))
