"""Timeline action handler — builds SVG Gantt/timeline charts.

Lazy-imports the heavy timeline builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action


@register_action(
    "report",
    "timeline",
    help_text="""Build an SVG Gantt/timeline chart.
Required: title, data ([{label, start, end, status}, ...])
Optional: config (width, bar_height, row_gap, theme)
Returns: {type, title, html_path, events}""",
    examples=[
        'report(action="timeline", title="Project Plan", data=[{"label":"Phase 1","start":"2026-01-01","end":"2026-02-15","status":"done"}])',
    ],
)
def run_timeline(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a timeline chart. Delegates to the heavy timeline builder."""
    from tools.report_core import timeline
    return timeline.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
