"""metrics/dbpa.py -- DBPA (Dívida Bruta por Ação) + P/DB (Price-to-Gross-Debt-per-Share) metric.

DBPA = debt / shares              (per-share value, from debt + shares engines)
P/DB = price / DBPA               (price ratio, adds price engine)

The `debt` engine returns total Empréstimos e Financiamentos (loans + financing,
sum of BPP codes 2.01.04 + 2.02.01) — i.e. gross debt, not net debt. So this
metric expresses the firm's gross debt per outstanding share.

This metric produces BOTH:
  - DBPA (per-share value): gross debt per share, useful on its own
  - P/DB (price ratio):     tells you how the market values the firm
                            relative to its gross debt per share

Engines composed: price + debt + shares

Interpretation:
  - P/DB < 1:   market values the firm below its gross debt per share
                (potentially distressed, or priced for high deleveraging)
  - P/DB 1-3:   moderate
  - P/DB > 5:   market is comfortable with the debt load
  - P/DB = None when gross debt <= 0 or shares/price missing

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.dbpa import dbpa_at, p_db_at, dbpa_history
    d = dbpa_at("PETR4", "2024-06-30")   # -> 18.50 (gross debt per share)
    p = p_db_at("PETR4", "2024-06-30")   # -> 2.0 (P/DB ratio)
    h = dbpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# ── Per-share value: DBPA = debt / shares ────────────────────────────────────

def dbpa_at(company: str, date: str) -> float | None:
    """Compute DBPA (Dívida Bruta por Ação = gross debt per share) at a date.

    DBPA = gross debt / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        DBPA in BRL, or None if debt or shares are missing/zero.
    """
    debt = debt_at(company, date)
    if debt is None or debt == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return debt / shares


# ── Price ratio: P/DB = price / DBPA ─────────────────────────────────────────

def p_db_at(company: str, date: str) -> float | None:
    """Compute P/DB (Price-to-Gross-Debt-per-Share) at a specific date.

    P/DB = price / DBPA = price / (debt / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/DB ratio as float, or None if any component is missing or
        DBPA <= 0 (zero/negative debt → ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    dbpa = dbpa_at(company, date)
    if dbpa is None or dbpa <= 0:
        return None  # Zero/negative debt → P/DB is meaningless

    return price / dbpa


# ── History: daily series with DBPA + P/DB ───────────────────────────────────

def dbpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily DBPA + P/DB time series for a date range.

    Optimized: debt is a BPP snapshot that changes only when new ITR/DFP is
    filed (quarterly). Shares change annually. Price changes daily. So we:
    1. Get all debt snapshot periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent debt + shares
    4. Compute DBPA = debt / shares, then P/DB = price / DBPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "debt", "shares", "dbpa", "p_db"}
        sorted oldest-first. Entries with None DBPA/P_DB (negative debt,
        missing data) are included with dbpa=None, p_db=None so charts
        show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get debt snapshot periods (quarterly step function)
    debt_periods_list = debt_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent debt <= date
        debt = None
        debt = lookup_lte(debt_periods_list, date, "debt")

        # Find most recent shares <= date
        shares = None
        shares = lookup_lte(sh_periods, date, "shares")

        # Compute DBPA = debt / shares
        dbpa = None
        if debt is not None and debt > 0 and shares is not None and shares > 0:
            dbpa = debt / shares

        # Compute P/DB = price / DBPA
        p_db = None
        if dbpa is not None and dbpa > 0 and price > 0:
            p_db = price / dbpa

        result.append({
            "date": date,
            "price": price,
            "debt": debt,
            "shares": shares,
            "dbpa": dbpa,
            "p_db": p_db,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="dbpa",
    per_share_label="DBPA",
    per_share_key="dbpa",
    per_share_fn=dbpa_at,
    ratio_label="P/DB",
    ratio_key="p_db",
    ratio_fn=p_db_at,
    history_fn=dbpa_history,
    engines=["price", "debt", "shares"],
    category="per_share",
    aliases=["p_db", "pdb", "p/divida_bruta", "preco_divida_bruta", "dbps"],
))
