"""metrics/p_ev.py -- P/EV (Price-to-Enterprise-Value) valuation multiple.

P/EV = price / EV_per_share
     = price / (price + (debt - cash) / shares)
     = market_cap / enterprise_value

Enterprise Value (EV) is not a standalone engine — it's computed inline as
market_cap + debt - cash, where market_cap = price × shares. Per-share this
simplifies to: EV_per_share = price + (debt - cash) / shares.

This metric produces ONLY a price ratio (no standalone per-share value is
surfaced), because EV per share includes the price component itself —
exposing it as a per-share value would be circular.

Engines composed: price + debt + cash + shares

Interpretation:
  - P/EV < 1: market cap below EV (firm has more debt than cash, or low equity
              premium relative to creditor claims)
  - P/EV near 1: market cap ≈ EV (cash ≈ debt)
  - P/EV > 1: market cap above EV (net cash position — cash > debt)
  - P/EV = None when shares/price missing or EV_per_share <= 0

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.p_ev import p_ev_at, p_ev_history
    r = p_ev_at("PETR4", "2024-06-30")  # -> 0.85 (market_cap / EV)
    h = p_ev_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# ── Price ratio: P/EV = price / (price + (debt - cash) / shares) ─────────────

def p_ev_at(company: str, date: str) -> float | None:
    """Compute P/EV (Price-to-Enterprise-Value) at a specific date.

    P/EV = price / (price + (debt - cash) / shares)
         = market_cap / enterprise_value

    where enterprise_value = market_cap + debt - cash.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/EV ratio as float, or None if any component is missing or
        EV_per_share <= 0 (negative EV → ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    debt = debt_at(company, date)
    if debt is None:
        return None
    cash = cash_at(company, date)
    if cash is None:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    net_debt_per_share = (debt - cash) / shares
    ev_per_share = price + net_debt_per_share
    if ev_per_share <= 0:
        return None  # Negative EV → P/EV is meaningless

    return price / ev_per_share


# ── History: daily series with P/EV ──────────────────────────────────────────

def p_ev_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily P/EV time series for a date range.

    Optimized: debt and cash are BPP/BPA snapshots that change only when
    new ITR/DFP is filed (quarterly). Shares change annually. Price
    changes daily. So we:
    1. Get all debt snapshot periods (step function — ~4 per year)
    2. Get all cash snapshot periods (step function — ~4 per year)
    3. Get all shares periods (step function — ~1 per year)
    4. For each daily price, find the most recent debt + cash + shares
    5. Compute EV_per_share = price + (debt - cash) / shares,
       then P/EV = price / EV_per_share

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "debt", "cash", "shares", "ev_per_share",
                 "p_ev"} sorted oldest-first. Entries with None P_EV
        (missing data, negative EV) are included with p_ev=None so charts
        show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get debt snapshot periods (quarterly step function)
    debt_periods_list = debt_periods(company)

    # Get cash snapshot periods (quarterly step function)
    cash_periods_list = cash_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent debt <= date
        debt = None
        debt = lookup_lte(debt_periods_list, date, "debt")

        # Find most recent cash <= date
        cash = None
        cash = lookup_lte(cash_periods_list, date, "cash")

        # Find most recent shares <= date
        shares = None
        shares = lookup_lte(sh_periods, date, "shares")

        # Compute EV_per_share = price + (debt - cash) / shares
        ev_per_share = None
        if (debt is not None and cash is not None
            and shares is not None and shares > 0 and price > 0):
            ev_per_share = price + (debt - cash) / shares

        # Compute P/EV = price / EV_per_share
        p_ev = None
        if ev_per_share is not None and ev_per_share > 0 and price > 0:
            p_ev = price / ev_per_share

        result.append({
            "date": date,
            "price": price,
            "debt": debt,
            "cash": cash,
            "shares": shares,
            "ev_per_share": ev_per_share,
            "p_ev": p_ev,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="p_ev",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="P/EV",
    ratio_key="p_ev",
    ratio_fn=p_ev_at,
    history_fn=p_ev_history,
    engines=["price", "debt", "cash", "shares"],
    category="valuation",
    aliases=["pev", "p/ev", "preco_ev"],
))
