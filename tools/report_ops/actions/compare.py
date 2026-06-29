"""Compare action handler — builds side-by-side diff tables.

Lazy-imports the heavy compare builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "compare",
    help_text="""Build a side-by-side diff table with delta highlighting.
Required: title, data ({"before": ..., "after": ...})
Optional: config (before_label, after_label, key_col, theme)
Returns: {type, title, html_path, mode, rows}""",
    examples=[
        'report(action="compare", title="Price Change", data={"before":{"price":100}, "after":{"price":120}})',
        'report(action="compare", title="Portfolio Delta", data={"before":[...], "after":[...]}, config={"key_col":"ticker"})',
    ],
)
def run_compare(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a comparison report. Delegates to the heavy compare builder."""
    from tools.report_ops import compare
    return compare.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
