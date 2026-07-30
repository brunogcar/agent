"""metrics/ppa.py -- PPA (Passivo por Ação) + P/Passivo (Price-to-Liabilities-per-Share) metric.

PPA       = (total_assets - pl) / shares   (per-share value, derived)
P/Passivo = price / PPA                    (price ratio, adds price engine)

Total liabilities (Passivo) is not a standalone engine — it equals Ativo - PL
(accounting identity: Ativo = Passivo + PL, so Passivo = Ativo - PL). This
metric expresses that as a per-share value, then builds a price ratio on top.

Note: this is NOT the same as P/VPA (Price-to-Book). P/VPA divides price by
equity per share (PL / shares), whereas P/Passivo divides price by total
liabilities per share ((Ativo - PL) / shares). P/Passivo is meaningful when
comparing how the market values the firm's debt + payables structure.

This metric produces BOTH:
  - PPA (per-share value): total liabilities per share, useful on its own
  - P/Passivo (price ratio): tells you how the market values the firm
                              relative to its total liabilities per share

Engines composed: price + total_assets + pl + shares

Interpretation:
  - P/Passivo < 1: market values the firm below its total liabilities per share
                   (potentially distressed, or asset-rich with low debt)
  - P/Passivo 1-3: fair
  - P/Passivo > 5: expensive (high premium over creditor claims)
  - P/Passivo = None when total liabilities <= 0 or shares/price missing

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.ppa import ppa_at, p_passivo_at, ppa_history
    p = ppa_at("PETR4", "2024-06-30")        # -> 8.60 (total liabilities per share)
    r = p_passivo_at("PETR4", "2024-06-30")  # -> 4.45 (P/Passivo ratio)
    h = ppa_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: PPA = (total_assets - pl) / shares ──────────────────────

def ppa_at(company: str, date: str) -> float | None:
    """Compute PPA (Passivo por Ação = total liabilities per share) at a date.

    PPA = (Ativo Total - Patrimônio Líquido) / shares outstanding
        = Passivo Total / shares

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        PPA in BRL, or None if total_assets/pl/shares are missing/zero.
        Negative total liabilities are preserved (returns a negative
        per-share value); the price ratio uses this to decide whether
        P/Passivo is meaningful.
    """
    total_assets = total_assets_at(company, date)
    if total_assets is None:
        return None
    pl = pl_at(company, date)
    if pl is None:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    total_liabilities = total_assets - pl
    return total_liabilities / shares


# ── Price ratio: P/Passivo = price / PPA ─────────────────────────────────────

def p_passivo_at(company: str, date: str) -> float | None:
    """Compute P/Passivo (Price-to-Liabilities-per-Share) at a specific date.

    P/Passivo = price / PPA = price / ((Ativo - PL) / shares)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/Passivo ratio as float, or None if any component is missing or
        PPA <= 0 (zero/negative total liabilities → ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    ppa = ppa_at(company, date)
    if ppa is None or ppa <= 0:
        return None  # Zero/negative liabilities → P/Passivo is meaningless

    return price / ppa


# ── History: daily series with PPA + P/Passivo ───────────────────────────────

def ppa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily PPA + P/Passivo time series for a date range.

    Optimized: total_assets and pl are BPA/BPP snapshots that change only
    when new ITR/DFP is filed (quarterly). Shares change annually. Price
    changes daily. So we:
    1. Get all total_assets snapshot periods (step function — ~4 per year)
    2. Get all pl snapshot periods (step function — ~4 per year)
    3. Get all shares periods (step function — ~1 per year)
    4. For each daily price, find the most recent Ativo + PL + shares
    5. Compute PPA = (Ativo - PL) / shares, then P/Passivo = price / PPA

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "total_assets", "pl", "shares",
                 "ppa", "p_passivo"} sorted oldest-first. Entries with
        None PPA/P_PASSIVO (zero/negative liabilities, missing data) are
        included with ppa=None, p_passivo=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get total_assets snapshot periods (quarterly step function)
    ta_periods_list = total_assets_periods(company)

    # Get pl snapshot periods (quarterly step function)
    pl_periods_list = pl_periods(company)

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

        # Find most recent pl <= date
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

        # Compute PPA = (Ativo - PL) / shares
        ppa = None
        if (total_assets is not None and pl is not None
            and shares is not None and shares > 0):
            ppa = (total_assets - pl) / shares

        # Compute P/Passivo = price / PPA
        p_passivo = None
        if ppa is not None and ppa > 0 and price > 0:
            p_passivo = price / ppa

        result.append({
            "date": date,
            "price": price,
            "total_assets": total_assets,
            "pl": pl,
            "shares": shares,
            "ppa": ppa,
            "p_passivo": p_passivo,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="ppa",
    per_share_label="PPA",
    per_share_key="ppa",
    per_share_fn=ppa_at,
    ratio_label="P/Passivo",
    ratio_key="p_passivo",
    ratio_fn=p_passivo_at,
    history_fn=ppa_history,
    engines=["price", "total_assets", "pl", "shares"],
    category="per_share",
    aliases=["p_passivo", "ppassivo", "p/passivos", "preco_passivos", "pps", "p_liabilities"],
))
