"""Diagram action handler — builds Mermaid.js architecture diagrams.

Lazy-imports the heavy diagrams builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action


@register_action(
    "report",
    "diagram",
    help_text="""Build a Mermaid.js architecture diagram.
Required: title
Optional: data (mermaid syntax string or nodes/edges dict), config (diagram_type, theme)
Returns: {type, title, html_path, diagram_type}""",
    examples=[
        'report(action="diagram", title="Flow", data="flowchart TD\n A[Start] --> B[End]")',
        'report(action="diagram", title="Architecture", data={"nodes":[{"id":"A","label":"API"}], "edges":[{"from":"A","to":"B"}]}, config={"diagram_type":"flowchart"})',
    ],
)
def run_diagram(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a Mermaid diagram. Delegates to the heavy diagrams builder."""
    from tools.report_core import diagrams
    return diagrams.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
