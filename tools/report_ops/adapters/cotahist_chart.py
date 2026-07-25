"""adapters/cotahist_chart.py — Flatten COTAHIST query result → chart data.

Adapter:
  cotahist_close_chart — line chart of daily close price over time.

Queries COTAHIST for the given ticker (last N trading days) and produces a
single-series line chart of the close price. This is the simplest useful
price-history visualization.

The adapter accepts a COTAHIST query result directly:
    {"status":"ok", "rows":[{"refdate":"2025-07-01","close":38.5}, ...]}

Or a ticker string + config["limit"] (default 90 days):
    report(action="chart", data="PETR4",
           config={"chart_type":"line","adapter":"cotahist_close_chart","limit":90})

Usage:
  # Option A: query COTAHIST first, then pipe result to chart
  data_source(domain="b3", sub_domain="cotahist", mode="query",
              params='{"ticker":"PETR4","limit":90}')
  report(action="chart", title="PETR4 — 90 days",
         data=<cotahist query result>,
         config={"chart_type":"line","adapter":"cotahist_close_chart"})

  # Option B: pass ticker string — adapter queries COTAHIST internally
  report(action="chart", title="PETR4 — 90 days",
         data="PETR4",
         config={"chart_type":"line","adapter":"cotahist_close_chart","limit":90})
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter


@register_adapter("cotahist_close_chart")
def close_chart(result) -> dict:
    """Flatten COTAHIST query result (or ticker string) into close-price chart data.

    Produces: {"x": [dates oldest-first], "y": [close prices], "label": "Close"}

    Accepts:
      - dict: a COTAHIST query result {status, rows: [{refdate, close, ...}]}
      - str: a ticker — queries COTAHIST internally (uses config from caller)
    """
    # If a ticker string is passed, query COTAHIST internally
    if isinstance(result, str):
        ticker = result.strip().upper()
        try:
            from data_sources.b3.cotahist.query_engine import query as cotahist_query
            # Default 90 days; caller can override via config
            r = cotahist_query(ticker=ticker, limit=90, market_type=10)
            if r.get("status") != "ok":
                return {"x": [], "y": [], "_error": f"cotahist: {r.get('error', 'no data')}"}
            result = r
        except Exception as e:
            return {"x": [], "y": [], "_error": f"cotahist: {e}"}

    if not isinstance(result, dict):
        return {"x": [], "y": [], "_error": "cotahist_close_chart requires a dict or ticker string"}

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
