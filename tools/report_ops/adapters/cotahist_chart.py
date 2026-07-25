"""adapters/cotahist_chart.py — Flatten COTAHIST query result → chart data.

Adapter:
  cotahist_close_chart — line chart of daily close price over time.

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
