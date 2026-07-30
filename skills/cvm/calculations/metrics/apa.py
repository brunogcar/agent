"""metrics/apa.py -- APA (Ativo por Ação) + P/Ativo (Price-to-Assets-per-Share) metric.

APA     = total_assets / shares   (per-share value, from total_assets + shares engines)
P/Ativo = price / APA             (price ratio, adds price engine)

The `total_assets` engine returns Ativo Total (BPA top-level account code "1"),
i.e. the full asset side of the balance sheet (current + non-current). This
metric expresses that as a per-share value, then builds a price ratio on top.

Note: this is NOT the same as P/VPA (Price-to-Book). P/VPA divides price by
equity per share (PL / shares), whereas P/Ativo divides price by total assets
per share (Ativo / shares). P/Ativo is always <= P/VPA when the firm has debt
(Ativo > PL → Ativo/share > PL/share → price / (Ativo/share) < price / (PL/share)).

This metric produces BOTH:
  - APA (per-share value): total assets per share, useful on its own
  - P/Ativo (price ratio): tells you how the market values the firm
                            relative to its total asset base per share

Engines composed: price + total_assets + shares

Interpretation:
  - P/Ativo < 1: market values the firm below its total assets per share
                 (potentially cheap, asset-rich)
  - P/Ativo 1-2: fair
  - P/Ativo > 3: expensive (high intangible/franchise premium)
  - P/Ativo = None when total_assets <= 0 or shares/price missing

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.apa import apa_at, p_ativo_at, apa_history
    a = apa_at("PETR4", "2024-06-30")    # -> 32.40 (total assets per share)
    p = p_ativo_at("PETR4", "2024-06-30")  # -> 1.18 (P/Ativo ratio)
    h = apa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: APA = total_assets / shares ─────────────────────────────

def apa_at(company: str, date: str) -> float | None:
    """Compute APA (Ativo por Ação = total assets per share) at a date.

    APA = Ativo Total / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        APA in BRL, or None if total_assets or shares are missing/zero.
    """
    total_assets = total_assets_at(company, date)
    if total_assets is None or total_assets == 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return total_assets / shares


# ── Price ratio: P/Ativo = price / APA ───────────────────────────────────────

def p_ativo_at(company: str, date: str) -> float | None:
    """Compute P/Ativo (Price-to-Assets-per-Share) at a specific date.

    P/Ativo = price / APA = price / (Ativo Total / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/Ativo ratio as float, or None if any component is missing or
        APA <= 0 (zero/negative total assets → ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    apa = apa_at(company, date)
    if apa is None or apa <= 0:
        return None  # Zero/negative total assets → P/Ativo is meaningless

    return price / apa


# ── History: daily series with APA + P/Ativo ─────────────────────────────────

def apa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily APA + P/Ativo time series for a date range.

    Optimized: total_assets is a BPA snapshot that changes only when new
    ITR/DFP is filed (quarterly). Shares change annually. Price changes
    daily. So we:
    1. Get all total_assets snapshot periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent total_assets + shares
    4. Compute APA = Ativo / shares, then P/Ativo = price / APA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "total_assets", "shares", "apa", "p_ativo"}
        sorted oldest-first. Entries with None APA/P_ATIVO (negative total
        assets, missing data) are included with apa=None, p_ativo=None so
        charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get total_assets snapshot periods (quarterly step function)
    ta_periods_list = total_assets_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent total_assets <= date
        total_assets = None
        for tap in reversed(ta_periods_list):
            if tap["date"] <= date:
                total_assets = tap["total_assets"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute APA = Ativo / shares
        apa = None
        if total_assets is not None and total_assets > 0 and shares is not None and shares > 0:
            apa = total_assets / shares

        # Compute P/Ativo = price / APA
        p_ativo = None
        if apa is not None and apa > 0 and price > 0:
            p_ativo = price / apa

        result.append({
            "date": date,
            "price": price,
            "total_assets": total_assets,
            "shares": shares,
            "apa": apa,
            "p_ativo": p_ativo,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="apa",
    per_share_label="APA",
    per_share_key="apa",
    per_share_fn=apa_at,
    ratio_label="P/Ativo",
    ratio_key="p_ativo",
    ratio_fn=p_ativo_at,
    history_fn=apa_history,
    engines=["price", "total_assets", "shares"],
    category="per_share",
    aliases=["p_ativo", "pativo", "p/ativos", "preco_ativos", "aps", "p_assets"],
))
