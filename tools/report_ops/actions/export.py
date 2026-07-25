"""Export action handler — exports HTML to PDF/PNG via Playwright.

Lazy-imports the heavy export runner to keep MCP startup fast.
Playwright is optional — if not installed, returns a graceful warning.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "export",
    help_text="""Export to PDF/PNG (from an HTML file) or xlsx (from table data).
Formats:
  pdf/png — data = path to an existing HTML report. config: {format, width, height}
  xlsx    — data = table-shape dict OR skill result (with config['adapter']) OR .json path.
            config: {format:"xlsx", adapter?: "financials_quarterly"|...}
            Each section becomes a sheet; numeric cells stay native + Excel-formatted.
Requires: playwright (pdf/png) or openpyxl (xlsx). Graceful warning if missing.
Returns: {status, html_path|pdf_path|png_path|xlsx_path, sheets?, warning?}""",
    examples=[
        'report(action="export", data="workspace/reports/trace-123/report.html", config={"format":"pdf"})',
        'report(action="export", data="reports/trace-123/dashboard.html", config={"format":"png"})',
        'report(action="export", data=<financials skill JSON>, config={"format":"xlsx","adapter":"financials_quarterly"})',
        'report(action="export", data=<table-shape dict>, config={"format":"xlsx"})',
    ],
)
def run_export(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Export HTML to PDF/PNG. Delegates to the heavy export runner."""
    from tools.report_ops import export
    return export.run(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
