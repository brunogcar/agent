"""adapters/cotahist.py — Flatten COTAHIST query result → chart data.

Adapters:
  cotahist_close_chart        — line chart of daily close price over time.
  cotahist_candlestick_chart  — OHLC candlestick chart of daily prices.

Accepts a COTAHIST query result dict:
    {"status":"ok", "rows":[{"refdate":"2025-07-01","close":38.5}, ...]}

Usage (2-step pattern — query COTAHIST first, then pipe to chart):
  data_source(domain="b3", sub_domain="cotahist", mode="query",
              params='{"ticker":"PETR4","limit":90}')
  # -> <cotahist query result JSON>

  report(action="chart", title="PETR4 — 90 days",
         data=<cotahist query result>,
         config={"chart_type":"line","adapter":"cotahist_close_chart"})

Note: all report adapters receive dicts (the registry's apply_adapter rejects
non-dict input). To chart a ticker's price history, query COTAHIST first via
the data_source tool, then pass the result to the chart action.

File history: cotahist_chart.py was renamed to cotahist.py (preserving git
history) and cotahist_candlestick.py was merged in (then deleted).
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter


@register_adapter("cotahist_close_chart")
def close_chart(result: dict) -> dict:
    """Flatten COTAHIST query result into close-price chart data.

    Produces: {"x": [dates oldest-first], "y": [close prices]}

    Args:
        result: a COTAHIST query result {status, rows: [{refdate, close, ...}]}
    """
    if not isinstance(result, dict):
        return {"x": [], "y": [],
                "_error": f"cotahist_close_chart requires a dict, got {type(result).__name__}"}

    if result.get("status") != "ok":
        return {"x": [], "y": [], "_error": result.get("error", "cotahist query failed")}

    rows = result.get("rows") or []
    if not rows:
        return {"x": [], "y": [], "_error": "no rows in cotahist result"}

    # Sort oldest-first by refdate (COTAHIST returns newest-first)
    sorted_rows = sorted(rows, key=lambda r: r.get("refdate", ""))
    x_labels = [r.get("refdate", "") for r in sorted_rows]
    close_values = [r.get("close") for r in sorted_rows]

    return {"x": x_labels, "y": close_values}


# ── cotahist_candlestick_chart adapter ─────────────────────────────────────
# (Merged from cotahist_candlestick.py — preserves the candlestick shape.)

@register_adapter("cotahist_candlestick_chart")
def candlestick_chart(result: dict) -> dict:
    """Flatten COTAHIST query result into OHLC candlestick chart config.

    Produces a Chart.js config dict (not the standard {x,y} shape) because
    candlestick charts need {t, o, h, l, c} data points. The charts builder
    detects this and renders it directly.

    Args:
        result: a COTAHIST query result {status, rows: [{refdate, open, high,
                low, close, ...}]}
    """
    if not isinstance(result, dict):
        return {"x": [], "y": [], "_error": f"requires dict, got {type(result).__name__}"}

    if result.get("status") != "ok":
        return {"x": [], "y": [], "_error": result.get("error", "cotahist query failed")}

    rows = result.get("rows") or []
    if not rows:
        return {"x": [], "y": [], "_error": "no rows in cotahist result"}

    # Sort oldest-first by refdate
    sorted_rows = sorted(rows, key=lambda r: r.get("refdate", ""))

    # Build OHLC data points: {t: date, o: open, h: high, l: low, c: close}
    ohlc_data = []
    for r in sorted_rows:
        refdate = r.get("refdate", "")
        o = r.get("open")
        h = r.get("high")
        l = r.get("low")
        c = r.get("close")
        if None in (o, h, l, c):
            continue  # skip incomplete rows
        ohlc_data.append({"t": refdate, "o": o, "h": h, "l": l, "c": c})

    if not ohlc_data:
        return {"x": [], "y": [], "_error": "no complete OHLC rows"}

    # Return a special shape that charts._to_chartjs_config detects as candlestick
    return {"_candlestick": True, "ohlc_data": ohlc_data}
