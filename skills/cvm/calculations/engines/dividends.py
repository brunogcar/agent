"""engines/dividends.py -- DPA (Dividends Per Share) TTM engine.

Gets trailing twelve months dividends per share at any historical date from
the B3 dividends database (cash_dividends table).

DPA TTM ALGORITHM
-----------------
For a date D, sum all cash dividends with an event date in [D - 365, D]:
  DPA_TTM = SUM(cash_dividends.rate WHERE event_date BETWEEN D-365 AND D)

The `rate` field in B3 cash_dividends is already per-share (R$/share), so we
just sum the rates in the 12-month window. No shares outstanding needed.

DATE RESOLUTION (v1.3.1 fix)
-----------------------------
The B3 dividends API returns three dates, but `paymentDate` is often NULL for
older dividends. We use COALESCE to pick the best available date:

  event_date = COALESCE(payment_date, last_date_prior, approved_on)

  - payment_date:   when the dividend was actually paid (often NULL for old data)
  - last_date_prior: ex-dividend date (most relevant for yield — must own stock
                     before this date to receive the dividend)
  - approved_on:    when the board declared the dividend (always populated)

This fallback dramatically increases data coverage. Without it, only recent
dividends (with payment_date set) are counted — older ones are missed.

JCP (Juros sobre Capital Próprio) is included — it's a real cash distribution
to shareholders, so it counts as a dividend for yield purposes. The label
field distinguishes Dividendo vs JCP, but we sum both.

DATA SOURCE
-----------
B3 dividends API (synced to dividends.db)
  - Table: cash_dividends
  - Fields: ticker, rate (R$/share), payment_date, last_date_prior, approved_on, label

DATA RANGE
----------
B3 dividends data goes back to ~2010 (varies per ticker). Some companies have
decades of history, others only recent years.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dividends import dividends_at, dividends_periods
    d = dividends_at("PETR4", "2024-06-30")  # -> 1.85 (R$/share TTM)
    ps = dividends_periods("PETR4")          # -> [{date, dpa}, ...]
"""

from __future__ import annotations

from datetime import datetime, timedelta
from skills._base import engine_cached  # [v1.8 F7]


# SQL expression for the best available date (v1.3.1 fix).
# payment_date is often NULL for older dividends — fall back to
# last_date_prior (ex-dividend date), then approved_on (declaration date).
_EVENT_DATE_EXPR = "COALESCE(payment_date, last_date_prior, approved_on)"


def _sum_dividends_in_window(ticker: str, date_to: str, days: int = 365) -> float:
    """Sum cash dividend rates in the trailing N-day window ending at date_to.

    Uses COALESCE(payment_date, last_date_prior, approved_on) as the event date
    so that older dividends without payment_date are still counted.

    Args:
        ticker: B3 ticker (PETR4).
        date_to: End date (YYYY-MM-DD). Inclusive.
        days: Window size in days. Default: 365 (TTM).

    Returns:
        Sum of rates (R$/share) in the window. 0.0 if no dividends.
    """
    try:
        from data_sources.b3.dividends.catalog import connect
    except (ImportError, FileNotFoundError):
        return 0.0

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return 0.0

    try:
        date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
        date_from = (date_to_dt - timedelta(days=days)).strftime("%Y-%m-%d")

        row = conn.execute(
            f"SELECT COALESCE(SUM(rate), 0) as total "
            f"FROM cash_dividends "
            f"WHERE ticker = ? AND {_EVENT_DATE_EXPR} IS NOT NULL "
            f"AND {_EVENT_DATE_EXPR} >= ? AND {_EVENT_DATE_EXPR} <= ?",
            (ticker.strip().upper(), date_from, date_to),
        ).fetchone()
        return float(row["total"]) if row else 0.0
    except Exception:
        return 0.0
    finally:
        conn.close()


def _get_all_event_dates(ticker: str) -> list[str]:
    """Get all distinct dividend event dates for a ticker, sorted oldest-first.

    Uses COALESCE(payment_date, last_date_prior, approved_on) as the event date.

    Returns: ["2010-03-15", "2010-06-30", ...] — dates where dividends occurred.
    Used to build the step function (DPA changes only on event dates).
    """
    try:
        from data_sources.b3.dividends.catalog import connect
    except (ImportError, FileNotFoundError):
        return []

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return []

    try:
        rows = conn.execute(
            f"SELECT DISTINCT {_EVENT_DATE_EXPR} as event_date "
            f"FROM cash_dividends "
            f"WHERE ticker = ? AND {_EVENT_DATE_EXPR} IS NOT NULL "
            f"ORDER BY event_date ASC",
            (ticker.strip().upper(),),
        ).fetchall()
        return [r["event_date"] for r in rows if r["event_date"]]
    except Exception:
        return []
    finally:
        conn.close()


@engine_cached
def dividends_at(ticker: str, date: str) -> float | None:
    """Get trailing twelve months dividends per share ending at or before date.

    DPA_TTM = SUM(cash_dividends.rate WHERE event_date BETWEEN date-365 AND date)

    Where event_date = COALESCE(payment_date, last_date_prior, approved_on).

    Args:
        ticker: B3 ticker (PETR4).
        date: YYYY-MM-DD.

    Returns:
        DPA TTM in BRL per share, or None if no dividends data.
        Returns 0.0 if the company pays no dividends (different from None
        which means "no data available").
    """
    total = _sum_dividends_in_window(ticker, date, days=365)
    if total == 0.0:
        # Distinguish "no data" from "company pays no dividends"
        event_dates = _get_all_event_dates(ticker)
        if not event_dates:
            return None  # No data at all
        # Check if there are any dividends BEFORE this date (company exists in DB)
        dates_before = [d for d in event_dates if d <= date]
        if not dates_before:
            return None  # No dividends before this date — can't compute TTM
        return 0.0  # Company exists but paid nothing in the window
    return total


@engine_cached
def dividends_periods(ticker: str) -> list[dict]:
    """Get all DPA TTM periods for a ticker.

    Returns: [{"date": "2024-06-30", "dpa": 1.85}, ...] sorted oldest-first.
    Each entry represents a point where DPA changed (a new dividend occurred).
    Between event dates, DPA is constant.

    Useful for building step-function DPA overlays on price charts.
    """
    event_dates = _get_all_event_dates(ticker)
    if not event_dates:
        return []

    periods = []
    for date in event_dates:
        dpa = dividends_at(ticker, date)
        if dpa is not None:
            periods.append({"date": date, "dpa": dpa})

    return periods


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="dividends",
    quantity="dpa",
    at_fn=dividends_at,
    periods_fn=dividends_periods,
    source="B3 cash_dividends (rate R$/share, event_date = COALESCE(payment_date, last_date_prior, approved_on))",
    category="market",
))
