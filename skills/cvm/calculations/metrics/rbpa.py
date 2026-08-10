"""metrics/rbpa.py -- RBPA (Resultado Bruto por Ação) + P/RB (Price-to-Gross-Profit) metric.

RBPA = gross_profit / shares   (per-share value, from gross_profit + shares engines)
P/RB = price / RBPA            (price ratio, adds price engine)

This metric produces BOTH:
  - RBPA (per-share value): gross profit per share, useful on its own
  - P/RB (price ratio):     tells you if the stock is cheap vs history

Mirrors metrics/lpa.py with two substitutions:
  - earnings engine → gross_profit engine (TTM Lucro Bruto instead of TTM net income)
  - LPA / P/L labels → RBPA / P/RB labels

Engines composed: price + gross_profit + shares

Interpretation:
  - P/RB < 4:  cheap
  - P/RB 4-8:  fair
  - P/RB 8-12: expensive
  - P/RB > 12: very expensive
  - P/RB = None when gross profit <= 0 (negative gross profit -- ratio meaningless)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.rbpa import rbpa_at, p_rb_at, rbpa_history
    r = rbpa_at("PETR4", "2024-06-30")   # -> 18.50 (gross profit per share)
    p = p_rb_at("PETR4", "2024-06-30")   # -> 2.1 (P/RB ratio)
    h = rbpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.dre.gross_profit import gross_profit_at, gross_profit_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# ── Per-share value: RBPA = gross_profit / shares ────────────────────────────

def rbpa_at(company: str, date: str) -> float | None:
    """Compute RBPA (Resultado Bruto por Ação = gross profit per share) at a date.

    RBPA = TTM gross profit / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        RBPA in BRL, or None if gross profit or shares are missing/zero.
    """
    gross_profit = gross_profit_at(company, date)
    if gross_profit is None or gross_profit == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return gross_profit / shares


# ── Price ratio: P/RB = price / RBPA ─────────────────────────────────────────

def p_rb_at(company: str, date: str) -> float | None:
    """Compute P/RB (Price-to-Gross-Profit) at a specific date.

    P/RB = price / RBPA = price / (TTM gross profit / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/RB ratio as float, or None if any component is missing or
        RBPA <= 0 (negative gross profit -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    rbpa = rbpa_at(company, date)
    if rbpa is None or rbpa <= 0:
        return None  # Negative/zero gross profit → P/RB is meaningless

    return price / rbpa


# ── History: daily series with RBPA + P/RB ───────────────────────────────────

def rbpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily RBPA + P/RB time series for a date range.

    Optimized: TTM gross profit changes only when new ITR/DFP is filed
    (quarterly). Shares change annually. Price changes daily. So we:
    1. Get all TTM gross profit periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent TTM gross profit + shares
    4. Compute RBPA = TTM GP / shares, then P/RB = price / RBPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "ttm_gp", "shares", "rbpa", "p_rb"}
        sorted oldest-first. Entries with None RBPA/P_RB (negative gross
        profit, missing data) are included with rbpa=None, p_rb=None so
        charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM gross profit periods (quarterly step function)
    gp_periods_list = gross_profit_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM gross profit <= date
        ttm_gp = None
        ttm_gp = lookup_lte(gp_periods_list, date, "ttm_gp")

        # Find most recent shares <= date
        shares = None
        shares = lookup_lte(sh_periods, date, "shares")

        # Compute RBPA = TTM GP / shares
        rbpa = None
        if ttm_gp is not None and ttm_gp > 0 and shares is not None and shares > 0:
            rbpa = ttm_gp / shares

        # Compute P/RB = price / RBPA
        p_rb = None
        if rbpa is not None and rbpa > 0 and price > 0:
            p_rb = price / rbpa

        result.append({
            "date": date,
            "price": price,
            "ttm_gp": ttm_gp,
            "shares": shares,
            "rbpa": rbpa,
            "p_rb": p_rb,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="rbpa",
    per_share_label="RBPA",
    per_share_key="rbpa",
    per_share_fn=rbpa_at,
    ratio_label="P/RB",
    ratio_key="p_rb",
    ratio_fn=p_rb_at,
    history_fn=rbpa_history,
    engines=["price", "gross_profit", "shares"],
    category="per_share",
    aliases=["p_rb", "prb", "p/resultado_bruto", "preco_resultado_bruto", "rbps"],
))
