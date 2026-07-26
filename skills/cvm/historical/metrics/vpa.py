"""metrics/vpa.py -- VPA (Valor Patrimonial por Ação) + P/VPA (Price-to-Book) metric.

VPA   = PL / shares                (per-share value, from pl + shares engines)
P/VPA = price / VPA                (price ratio, adds price engine)

This metric produces BOTH:
  - VPA (per-share value): book value per share, useful on its own
  - P/VPA (price ratio):   tells you if the stock is cheap vs history

Engines composed: price + pl + shares

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.metrics.vpa import vpa_at, pvpa_at, vpa_history
    vpa  = vpa_at("PETR4", "2024-06-30")    # -> 23.85
    pvpa = pvpa_at("PETR4", "2024-06-30")   # -> 1.45
    h    = vpa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.historical.engines.price import price_at, price_series
from skills.cvm.historical.engines.pl import pl_at, pl_periods
from skills.cvm.historical.engines.shares import shares_at, shares_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


# ── Per-share value: VPA = PL / shares ───────────────────────────────────────

def vpa_at(company: str, date: str) -> float | None:
    """Compute VPA (Valor Patrimonial por Ação = book value per share) at a date.

    VPA = Patrimônio Líquido / shares outstanding

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        VPA in BRL, or None if PL or shares are missing/zero.
    """
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None  # Negative equity — VPA is meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return pl / shares


# ── Price ratio: P/VPA = price / VPA ─────────────────────────────────────────

def pvpa_at(company: str, date: str) -> float | None:
    """Compute P/VPA (Price-to-Book) at a specific date.

    P/VPA = price / VPA = price / (PL / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/VPA ratio as float, or None if any component is missing or VPA <= 0.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    vpa = vpa_at(company, date)
    if vpa is None or vpa <= 0:
        return None  # Negative equity — P/VPA is meaningless

    return price / vpa


# ── History: daily series with VPA + P/VPA ───────────────────────────────────

def vpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily VPA + P/VPA time series for a date range.

    Optimized: PL changes only when a new BPP snapshot is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all PL periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent PL + shares
    4. Compute VPA = PL / shares, then P/VPA = price / VPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "pl", "shares", "vpa", "pvpa"}
        sorted oldest-first. Entries with None VPA/PVPA (negative equity,
        missing data) are included with vpa=None, pvpa=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get PL periods (quarterly step function)
    pl_periods_list = pl_periods(company)

    # Get shares periods (annual step function)
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

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute VPA = PL / shares
        vpa = None
        if pl is not None and pl > 0 and shares is not None and shares > 0:
            vpa = pl / shares

        # Compute P/VPA = price / VPA
        pvpa = None
        if vpa is not None and vpa > 0 and price > 0:
            pvpa = price / vpa

        result.append({
            "date": date,
            "price": price,
            "pl": pl,
            "shares": shares,
            "vpa": vpa,
            "pvpa": pvpa,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="vpa",
    per_share_label="VPA",
    per_share_key="vpa",
    per_share_fn=vpa_at,
    ratio_label="P/VPA",
    ratio_key="pvpa",
    ratio_fn=pvpa_at,
    history_fn=vpa_history,
    engines=["price", "pl", "shares"],
    aliases=["pvpa", "p/vpa", "preco_vpa", "p_vpa"],
))
