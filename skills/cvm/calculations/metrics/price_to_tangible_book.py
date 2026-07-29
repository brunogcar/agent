"""metrics/price_to_tangible_book.py -- Tangible Book Value per Share + P/Tangible Book metric.

Tangible Book / Ação = (PL - Intangibles) / shares   (per-share value)
P/Tangible Book      = price / Tangible Book          (price ratio)

This metric produces BOTH:
  - VPA Tangível (per-share value): tangible book value per share --
    equity per share excluding goodwill and other intangibles. Useful
    on its own as a conservative book-value measure (excludes assets
    that may not be realizable in liquidation).
  - P/VPA Tangível (price ratio): tells you how much you are paying
    per BRL of TANGIBLE equity. More conservative than P/VPA --
    companies with significant goodwill (acquisition-heavy) will show
    a much higher P/Tangible Book than P/VPA.

Mirrors metrics/vpa.py with one change: subtracts `intangibles` from
`pl` before dividing by shares.

Intangibles is sourced from the `intangibles` engine (BPA codigo 1.02.04)
-- includes goodwill from business combinations, intellectual property,
brand value, software, etc. Excluded because these assets may have
limited liquidation value and are hard to value objectively.

Engines composed: price + pl + intangibles + shares.

Interpretation:
  - P/Tangible Book < 1.0: stock trades below tangible book -- potential
    value play (or value trap -- investigate WHY)
  - P/Tangible Book 1.0-3.0: reasonable
  - P/Tangible Book > 5.0: expensive vs tangible book (may be justified
    for asset-light / high-ROE businesses)
  - Returns None when PL <= 0, shares <= 0, (PL - Intangibles) <= 0
    (intangibles consume all equity -- tangible equity negative), or
    Tangible Book per Share <= 0

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.price_to_tangible_book import (
        tangible_book_ps_at, p_tangible_book_at, p_tangible_book_history,
    )
    tbps = tangible_book_ps_at("PETR4", "2024-06-30")  # -> 18.50
    ptb  = p_tangible_book_at("PETR4", "2024-06-30")   # -> 2.05
    h    = p_tangible_book_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations.engines.intangibles import intangibles_at, intangibles_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: Tangible Book / Ação = (PL - Intangibles) / shares ──────

def tangible_book_ps_at(company: str, date: str) -> float | None:
    """Compute Tangible Book Value per Share at a specific date.

    Tangible Book / Ação = (Patrimônio Líquido - Intangível) / shares

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Tangible book value per share in BRL, or None if:
          - PL is None or <= 0
          - shares is None or <= 0
          - intangibles is None (treated as 0 would hide missing-data
            from callers -- return None for honesty instead)
          - (PL - Intangibles) <= 0 (tangible equity consumed by
            intangibles -- ratio meaningless)
    """
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None  # Negative equity -- ratio is meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    intangibles = intangibles_at(company, date)
    if intangibles is None:
        return None  # Don't silently substitute 0 -- let callers see missing data

    tangible_equity = pl - intangibles
    if tangible_equity <= 0:
        return None  # Intangibles consume all equity -- ratio meaningless

    return tangible_equity / shares


# ── Price ratio: P/Tangible Book = price / Tangible Book per Share ───────────

def p_tangible_book_at(company: str, date: str) -> float | None:
    """Compute P/Tangible Book (Price-to-Tangible-Book) at a specific date.

    P/Tangible Book = price / ((PL - Intangibles) / shares)
                   = price × shares / (PL - Intangibles)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/Tangible Book ratio as float, or None if any component is
        missing, price <= 0, or Tangible Book per Share <= 0 (negative
        tangible equity -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    tangible_book_ps = tangible_book_ps_at(company, date)
    if tangible_book_ps is None or tangible_book_ps <= 0:
        return None  # Negative/zero tangible book -- ratio meaningless

    return price / tangible_book_ps


# ── History: daily series with Tangible Book + P/Tangible Book ───────────────

def p_tangible_book_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily Tangible Book + P/Tangible Book time series for a date range.

    Optimized: PL changes only when a new BPP snapshot is filed
    (quarterly). Intangibles similarly step quarterly. Shares change
    annually. Price changes daily. So we:
    1. Get all PL periods (step function -- ~4 per year)
    2. Get all intangibles periods (step function -- ~4 per year)
    3. Get all shares periods (step function -- ~1 per year)
    4. For each daily price, find the most recent PL + intangibles +
       shares, compute Tangible Book = (PL - Intangibles) / shares,
       then P/Tangible Book = price / Tangible Book.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "pl", "intangibles", "shares",
                 "tangible_book_ps", "p_tangible_book"}
        sorted oldest-first. Entries with None ratio (negative tangible
        equity, missing data) are included with None values so charts
        show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get step-function periods for snapshot/annual engines
    pl_periods_list = pl_periods(company)
    intan_periods_list = intangibles_periods(company)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent PL <= date
        pl = None
        for pp in reversed(pl_periods_list):
            if pp["date"] <= date:
                pl = pp["pl"]
                break

        # Find most recent intangibles <= date
        intangibles = None
        for ip in reversed(intan_periods_list):
            if ip["date"] <= date:
                intangibles = ip["intangibles"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute Tangible Book per Share = (PL - Intangibles) / shares
        tangible_book_ps = None
        if (pl is not None and pl > 0
                and intangibles is not None
                and shares is not None and shares > 0):
            tangible_equity = pl - intangibles
            if tangible_equity > 0:
                tangible_book_ps = tangible_equity / shares

        # Compute P/Tangible Book = price / Tangible Book per Share
        p_tangible_book = None
        if (tangible_book_ps is not None and tangible_book_ps > 0
                and price is not None and price > 0):
            p_tangible_book = price / tangible_book_ps

        result.append({
            "date": date,
            "price": price,
            "pl": pl,
            "intangibles": intangibles,
            "shares": shares,
            "tangible_book_ps": tangible_book_ps,
            "p_tangible_book": p_tangible_book,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="price_to_tangible_book",
    per_share_label="VPA Tangível",
    per_share_key="tangible_book_ps",
    per_share_fn=tangible_book_ps_at,
    ratio_label="P/VPA Tangível",
    ratio_key="p_tangible_book",
    ratio_fn=p_tangible_book_at,
    history_fn=p_tangible_book_history,
    engines=["price", "pl", "intangibles", "shares"],
    category="valuation",
    aliases=["p_vpa_tangivel", "ptb", "price_tangible_book"],
))
