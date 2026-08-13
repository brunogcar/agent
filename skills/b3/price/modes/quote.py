"""Mode: quote -- Latest OHLCV snapshot + 52-week range.

Simple mode: fetches latest available quote + 52-week high/low and returns
them as a small KPI set. No charts, no full series.
"""
from __future__ import annotations

from datetime import date as _date, timedelta as _timedelta

from skills.b3.price._registry import register_mode
from skills.b3.price.engines import latest_quote, compute_52w_range, ohlcv_series
from skills.b3.price.report import build_quote_kpis


@register_mode(
    "quote",
    description=(
        "Latest OHLCV snapshot for a B3 ticker + 52-week high/low. "
        "Returns a compact KPI list (no charts)."
    ),
    params={"ticker": "str. Required. B3 ticker (e.g. PETR4)."},
    include_in_all=False,
    examples=[
        'skill(domain="b3", sub_domain="price", mode="quote", '
        'params=\'{"ticker":"PETR4"}\')',
    ],
)
def quote(ticker: str = "") -> dict:
    """Return the latest quote + 52w range for a single ticker."""
    if not ticker or not ticker.strip():
        return {"status": "error", "error": "ticker is required"}

    tk = ticker.strip().upper()
    today = _date.today().isoformat()
    range_52w = compute_52w_range(tk, today)
    q = latest_quote(tk)

    if not q:
        return {
            "status": "not_found",
            "ticker": tk,
            "error": f"no quote data for {tk}",
        }

    # Previous close: query the OHLCV series for the last 5 days and take
    # the second-to-last close.
    date_from = (_date.today() - _timedelta(days=14)).isoformat()
    series = ohlcv_series(tk, date_from, today)
    prev_close = None
    if len(series) >= 2:
        prev_close = series[-2].get("close")

    kpis = build_quote_kpis(q, prev_close, range_52w)

    return {
        "status": "ok",
        "ticker": tk,
        "quote": q,
        "range_52w": range_52w,
        "prev_close": prev_close,
        "kpis": kpis,
    }
