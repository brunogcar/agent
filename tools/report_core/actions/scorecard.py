"""Scorecard action handler — builds RAG status dashboards with radar charts.

Lazy-imports the heavy scorecard builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action


@register_action(
    "report",
    "scorecard",
    help_text="""Build a RAG status dashboard with radar chart.
Required: title, data ([{name, score, target, weight}, ...])
Optional: config (theme, accent)
Returns: {type, title, html_path, dimensions, overall_score}""",
    examples=[
        'report(action="scorecard", title="Health Check", data=[{"name":"CPU","score":85,"target":90,"weight":1.0}])',
    ],
)
def run_scorecard(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a scorecard dashboard. Delegates to the heavy scorecard builder."""
    from tools.report_core import scorecard
    return scorecard.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
