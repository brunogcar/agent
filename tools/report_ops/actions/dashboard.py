"""Dashboard action handler — builds a multi-panel dashboard.

Lazy-imports the heavy html builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "dashboard",
    help_text="""Build a multi-panel dashboard with tabs and KPIs.
Required: title
Optional: data (dict/list or file path), config (tabs, kpis, charts, columns, theme)
Returns: {type, title, html_path, tabs, charts}""",
    examples=[
        'report(action="dashboard", title="System Health", config={"tabs":[{"name":"Metrics","sections":[{"title":"CPU","type":"chart"}]}], "kpis":[{"label":"Uptime","value":"99.9%"}]})',
        'report(action="dashboard", title="Portfolio", data="workspace/holdings.csv", preset="financial")',
    ],
)
def run_dashboard(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a multi-panel dashboard. Delegates to html.build_dashboard."""
    from tools.report_ops import html
    return html.build_dashboard(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
