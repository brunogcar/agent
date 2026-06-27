"""Chart action handler — builds interactive Chart.js charts.

Lazy-imports the heavy charts builder to keep MCP startup fast.
No pandas, jinja2, or plotly imports at module level.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action


@register_action(
    "report",
    "chart",
    help_text="""Build an interactive Chart.js chart.
Required: title
Optional: data (dict/list or file path), config (chart_type, x_label, y_label, color, theme)
Returns: {type, title, html_path, chart_type}""",
    examples=[
        'report(action="chart", title="Revenue", data={"x":["Q1","Q2"], "y":[100,150]}, config={"chart_type":"bar"})',
        'report(action="chart", title="Users", data="workspace/metrics.csv", config={"chart_type":"line", "theme":"light"})',
    ],
)
def run_chart(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a Chart.js chart. Delegates to the heavy charts builder."""
    from tools.report_core import charts
    return charts.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
