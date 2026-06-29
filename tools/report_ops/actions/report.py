"""Report action handler — builds a single-scroll HTML report.

Lazy-imports the heavy html builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "report",
    help_text="""Build a single-scroll HTML report with sections.
Required: title
Optional: data (dict/list or file path), config (sections, kpis, sources, theme)
Returns: {type, title, html_path, sections}""",
    examples=[
        'report(action="report", title="Q3 Analysis", data={"revenue":150,"costs":80}, config={"sections":[{"title":"Overview","text":"Strong quarter"}]})',
        'report(action="report", title="Audit", data="workspace/findings.json", preset="code_audit")',
    ],
)
def run_report(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a single-scroll HTML report. Delegates to html.build_report."""
    from tools.report_ops import html
    return html.build_report(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
