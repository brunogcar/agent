"""metrics/vpa.py — P/VPA (Price-to-Book) historical metric.

P/VPA = price / (PL / shares)
      = price / VPA
      = price × shares / PL

Where:
  - price  = daily close (COTAHIST)            → changes daily
  - PL     = Patrimônio Líquido snapshot (DFP/ITR BPP 2.03) → changes quarterly
  - shares = shares outstanding (FRE/investsite) → changes annually

Each component comes from its own engine. This module is the composition layer
— it imports price + pl + shares engines and combines them.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.metrics.vpa import vpa_at, vpa_history
    v = vpa_at("PETR4", "2024-06-30")  # → 1.45
    h = vpa_history("PETR4", "2024-01-01", "2024-12-31")
"""

from __future__ import annotations

from skills.cvm.historical.engines.price import price_at, price_series
from skills.cvm.historical.engines.pl import pl_at, pl_periods
from skills.cvm.historical.engines.shares import shares_at, shares_periods


def vpa_at(company: str, date: str) -> float | None:
    """Compute P/VPA at a specific date.

    P/VPA = price / (PL / shares) = price × shares / PL

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/VPA ratio as float, or None if any component is missing or PL <= 0.
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None  # Negative equity — P/VPA is meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    vpa = pl / shares
    if vpa <= 0:
        return None  # Defensive — PL <= 0 already caught above

    return price / vpa


def vpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily P/VPA time series for a date range.

    Optimized: PL changes only when a new BPP snapshot is filed (quarterly).
    Shares change annually. Price changes daily. So we:
    1. Get all PL periods (step function — ~4 per year)
    2. Get all shares periods (step function — ~1 per year)
    3. For each daily price, find the most recent PL + shares
    4. Compute P/VPA = price / (PL / shares)

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date": "YYYY-MM-DD", "price": float, "pl": float,
                 "shares": int, "vpa": float} sorted oldest-first.
        Entries with None VPA (negative equity, missing data) are included
        with vpa=None so the chart shows gaps.
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

        # Compute P/VPA
        vpa = None
        if (
            pl is not None and pl > 0
            and shares is not None and shares > 0
            and price > 0
        ):
            book_value_per_share = pl / shares
            if book_value_per_share > 0:
                vpa = price / book_value_per_share

        result.append({
            "date": date,
            "price": price,
            "pl": pl,
            "shares": shares,
            "vpa": vpa,
        })

    return result
