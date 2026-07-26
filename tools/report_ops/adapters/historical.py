"""adapters/historical.py — Flatten historical skill JSON → chart/table data.

Adapters:
  historical_pe_chart — multi-series line chart of P/L over time with percentile bands
  historical_summary  — KPI strip + summary table (current vs averages + percentile)
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


@register_adapter("historical_pe_chart")
def pe_chart(result: dict) -> dict:
    """Flatten historical.pe_history result into a multi-series chart config.

    Produces the multi-series chart data shape:
        {"x": [dates], "datasets": [{"label": "P/L", "data": [values]}]}
    None P/L values are converted to null (Chart.js handles gaps).
    """
    if not _ok(result):
        return _error_table(result, title="Historical P/L")

    series = result.get("series") or []
    if not series:
        return _error_table(result, title="Historical P/L")

    x_labels = [s["date"] for s in series]
    pe_data = [s.get("pe") for s in series]  # None for gaps

    return {
        "x": x_labels,
        "datasets": [{"label": "P/L", "data": pe_data}],
    }


@register_adapter("historical_summary")
def summary(result: dict) -> dict:
    """Flatten historical.summary result into KPI strip + summary table."""
    if not _ok(result):
        return _error_table(result, title="Historical Summary")

    current = result.get("current", {})
    averages = result.get("averages", {})
    rng = result.get("range", {})

    # KPI strip
    kpis = [
        {"label": "Current P/L", "value": current.get("pe"), "format": "num"},
        {"label": "1Y Average", "value": averages.get("1y"), "format": "num"},
        {"label": "3Y Average", "value": averages.get("3y"), "format": "num"},
        {"label": "5Y Average", "value": averages.get("5y"), "format": "num"},
        {"label": "Percentile", "value": result.get("percentile"), "format": "num"},
    ]

    # Summary table
    columns = ["Metric", "Value"]
    rows = [
        ["Current P/L", apply_fmt(current.get("pe"), "num")],
        ["Current Price", apply_fmt(current.get("price"), "brl_full")],
        ["TTM Earnings", apply_fmt(current.get("ttm_earnings"), "brl")],
        ["Shares", apply_fmt(current.get("shares"), "int")],
        ["1Y Average P/L", apply_fmt(averages.get("1y"), "num")],
        ["3Y Average P/L", apply_fmt(averages.get("3y"), "num")],
        ["5Y Average P/L", apply_fmt(averages.get("5y"), "num")],
        ["Min P/L (5Y)", apply_fmt(rng.get("min"), "num")],
        ["Max P/L (5Y)", apply_fmt(rng.get("max"), "num")],
        ["Percentile", str(result.get("percentile", "")) + "%"],
        ["Interpretation", result.get("interpretation", "")],
    ]

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Historical P/L Summary — {result.get('company','')}",
            "columns": columns,
            "rows": rows,
            "formats": {"Metric": "text", "Value": "text"},
            "note": f"Date: {current.get('date','')} | Data points: {result.get('data_points',0)}",
        }],
        "kpis": kpis,
        "sources": [],
    }
