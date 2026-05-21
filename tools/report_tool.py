# tools/report_tool.py
"""
tools/report_tool.py — Report Meta-Tool.

WHY THIS FILE EXISTS:
---------------------
This is the LLM-facing entry point. It imports the actual logic from 
the tools/report/ package and exposes a clean @tool interface.

The @tool decorator requires this file to be at tools/ level for 
registry.py to discover it.
"""
from __future__ import annotations

from typing import Any

from registry import tool
from tools.report import build_dashboard, build_chart, build_map, load_data


@tool
def report(
    type: str,
    title: str = "",
    subtitle: str = "",
    # Dashboard params
    kpis: list[dict] | None = None,
    tables: list[dict] | None = None,
    tabs: list[dict] | None = None,
    accordions: list[dict] | None = None,
    text: str = "",
    # Chart params
    chart_type: str = "bar",
    data: dict | list | None = None,
    data_path: str = "",
    x_col: str = "",
    y_col: str = "",
    label_col: str = "",
    x_label: str = "",
    y_label: str = "",
    color: str = "",
    # Map params
    map_type: str = "markers",
    center_lat: float = 0.0,
    center_lon: float = 0.0,
    zoom: int = 5,
    # Common params
    accent: str = "#3b82f6",
    output: str = "",
    export_png: bool = False,
    export_pdf: bool = False,
) -> dict:
    """
    Generate interactive dashboards, charts, maps, and reports with Dark Mode.
    
    type: "dashboard" | "chart" | "map"
    
    ── DASHBOARD (Tabs, KPIs, Tables, Accordions, Markdown) ──────────────────
    kpis:   [{"label": "Revenue", "value": "R$1.2M", "delta": "+18%"}, ...]
    tables: [{"title": "Top Stocks", "data": [{"Ticker": "PETR4", "Price": "37.45"}]}, ...]
    tabs:   [{"label": "Overview", "text": "**Bold** markdown", "tables": [...], "accordions": [...]}]
    accordions: [{"title": "Show Code", "content": "```python\nprint('hi')\n```"}]
    text:   "Markdown text for main body (if not using tabs)."
    
    Example:
        report(type="dashboard", title="B3 Market",
               kpis=[{"label": "Volume", "value": "R$842B"}],
               tabs=[{"label": "Summary", "text": "Market is **bullish**."}])
    
    ── CHART ─────────────────────────────────────────────────────────────────
    chart_type: "bar" | "line" | "pie" | "scatter"
    data: {"x": [...], "y": [...]} or [1, 2, 3]
    data_path: "file.csv" with x_col="month", y_col="revenue"
    
    ── MAP ───────────────────────────────────────────────────────────────────
    map_type: "markers" | "heatmap" | "choropleth" | "route"
    data: {"lat": [...], "lon": [...], "labels": [...]}
    """
    vtype = type.strip().lower()
    
    if vtype == "dashboard":
        return build_dashboard(
            title=title, subtitle=subtitle, kpis=kpis, tables=tables,
            tabs=tabs, accordions=accordions, text=text, accent=accent,
            export_pdf_flag=export_pdf,
        )
    
    if vtype == "chart":
        loaded, err = load_data(data, data_path, x_col, y_col, label_col)
        if err:
            return {"status": "error", "error": err}
        return build_chart(
            chart_type=chart_type, data=loaded, title=title,
            x_label=x_label, y_label=y_label, color=color,
            output=output, export_png=export_png,
        )
    
    if vtype == "map":
        loaded, err = load_data(data, data_path)
        if err and data is None:
            return {"status": "error", "error": err}
        return build_map(
            map_type=map_type, data=loaded or data, title=title,
            center_lat=center_lat, center_lon=center_lon, zoom=zoom, output=output,
        )
    
    return {"status": "error", "error": f"Unknown type '{vtype}'. Use: dashboard | chart | map"}