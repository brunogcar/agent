"""Export action handler — exports HTML to PDF/PNG via Playwright.

Lazy-imports the heavy export runner to keep MCP startup fast.
Playwright is optional — if not installed, returns a graceful warning.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action


@register_action(
    "report",
    "export",
    help_text="""Export an existing HTML report to PDF or PNG.
Required: data (path to existing HTML file)
Optional: config (format, width, height)
Returns: {status, html_path, pdf_path, png_path, warning}""",
    examples=[
        'report(action="export", data="workspace/reports/trace-123/report.html", config={"format":"pdf"})',
        'report(action="export", data="reports/trace-123/dashboard.html", config={"format":"png"})',
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
    from tools.report_core import export
    return export.run(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
