"""adapters/cotahist_candlestick.py — Flatten COTAHIST query result → OHLC candlestick chart.

Adapter:
  cotahist_candlestick_chart — candlestick chart of daily OHLC from COTAHIST.

Produces Chart.js config with the candlestick type (requires chartjs-chart-financial
plugin, loaded via CDN in the chart template when chart_type="candlestick").

Usage (2-step pattern — query COTAHIST first, then pipe to chart):
  data_source(domain="b3", sub_domain="cotahist", mode="query",
              params='{"ticker":"PETR4","limit":60}')
  report(action="chart", title="PETR4 — 60 days",
         data=<cotahist query result>,
         config={"chart_type":"candlestick","adapter":"cotahist_candlestick_chart"})
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter


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
