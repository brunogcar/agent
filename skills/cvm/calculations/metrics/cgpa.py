"""metrics/cgpa.py -- CGPA (Capital de Giro por Ação) + P/CG (Price-to-Working-Capital) metric.

CGPA = (current_assets - current_liabilities) / shares  (per-share value)
P/CG = price / CGPA                                       (price ratio)

Working capital (capital de giro) = Ativo Circulante - Passivo Circulante.
This metric expresses that as a per-share value, then builds a price ratio
on top.

This metric produces BOTH:
  - CGPA (per-share value): working capital per share, useful on its own
  - P/CG (price ratio):     tells you how the market values the firm's
                            short-term operating liquidity per share

Engines composed: price + current_assets + current_liabilities + shares

Interpretation:
  - P/CG < 1:   market values the firm below its working capital per share
                (potentially cheap, but check whether WC is positive)
  - P/CG 1-5:   fair
  - P/CG > 10:  expensive
  - P/CG = None when working capital <= 0 (negative WC) or shares/price missing

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.cgpa import cgpa_at, p_cg_at, cgpa_history
    c = cgpa_at("PETR4", "2024-06-30")   # -> 4.20 (working capital per share)
    p = p_cg_at("PETR4", "2024-06-30")   # -> 9.0 (P/CG ratio)
    h = cgpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.bpa.current_assets import current_assets_at, current_assets_periods
from skills.cvm.calculations.engines.bpp.current_liabilities import (
    current_liabilities_at,
    current_liabilities_periods,
)
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: CGPA = (current_assets - current_liabilities) / shares ──

def cgpa_at(company: str, date: str) -> float | None:
    """Compute CGPA (Capital de Giro por Ação = working capital per share) at a date.

    CGPA = (Ativo Circulante - Passivo Circulante) / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        CGPA in BRL, or None if current_assets/current_liabilities/shares are
        missing/zero. Negative working capital is preserved (returns a
        negative per-share value); the price ratio uses this to decide
        whether P/CG is meaningful.
    """
    ca = current_assets_at(company, date)
    if ca is None:
        return None
    cl = current_liabilities_at(company, date)
    if cl is None:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    working_capital = ca - cl
    return working_capital / shares


# ── Price ratio: P/CG = price / CGPA ─────────────────────────────────────────

def p_cg_at(company: str, date: str) -> float | None:
    """Compute P/CG (Price-to-Working-Capital-per-Share) at a specific date.

    P/CG = price / CGPA = price / ((CA - CL) / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/CG ratio as float, or None if any component is missing or
        CGPA <= 0 (negative working capital → ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    cgpa = cgpa_at(company, date)
    if cgpa is None or cgpa <= 0:
        return None  # Negative/zero working capital → P/CG is meaningless

    return price / cgpa


# ── History: daily series with CGPA + P/CG ───────────────────────────────────

def cgpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily CGPA + P/CG time series for a date range.

    Optimized: current_assets and current_liabilities are BPA/BPP snapshots
    that change only when new ITR/DFP is filed (quarterly). Shares change
    annually. Price changes daily. So we:
    1. Get all current_assets snapshot periods (step function — ~4 per year)
    2. Get all current_liabilities snapshot periods (step function — ~4 per year)
    3. Get all shares periods (step function — ~1 per year)
    4. For each daily price, find the most recent CA + CL + shares
    5. Compute CGPA = (CA - CL) / shares, then P/CG = price / CGPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "current_assets", "current_liabilities",
                 "shares", "cgpa", "p_cg"} sorted oldest-first. Entries with
        None CGPA/P_CG (negative WC, missing data) are included with
        cgpa=None, p_cg=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get current_assets snapshot periods (quarterly step function)
    ca_periods_list = current_assets_periods(company)

    # Get current_liabilities snapshot periods (quarterly step function)
    cl_periods_list = current_liabilities_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent current_assets <= date
        ca = None
        for cap in reversed(ca_periods_list):
            if cap["date"] <= date:
                ca = cap["current_assets"]
                break

        # Find most recent current_liabilities <= date
        cl = None
        for clp in reversed(cl_periods_list):
            if clp["date"] <= date:
                cl = clp["current_liabilities"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute CGPA = (CA - CL) / shares
        cgpa = None
        if (ca is not None and cl is not None
            and shares is not None and shares > 0):
            cgpa = (ca - cl) / shares

        # Compute P/CG = price / CGPA
        p_cg = None
        if cgpa is not None and cgpa > 0 and price > 0:
            p_cg = price / cgpa

        result.append({
            "date": date,
            "price": price,
            "current_assets": ca,
            "current_liabilities": cl,
            "shares": shares,
            "cgpa": cgpa,
            "p_cg": p_cg,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="cgpa",
    per_share_label="CGPA",
    per_share_key="cgpa",
    per_share_fn=cgpa_at,
    ratio_label="P/CG",
    ratio_key="p_cg",
    ratio_fn=p_cg_at,
    history_fn=cgpa_history,
    engines=["price", "current_assets", "current_liabilities", "shares"],
    category="per_share",
    aliases=["p_cg", "pcg", "p/capital_giro", "preco_capital_giro", "wcps"],
))
