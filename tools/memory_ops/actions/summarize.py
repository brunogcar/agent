"""Summarize action — generate an LLM summary of top memories."""
from __future__ import annotations

from core.contracts import ok

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem

HELP_SUMMARIZE = """
summarize — Generate an LLM summary of top memories across collections.

Parameters:
  collections: Filter to specific collections. Omit for all.
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="summarize")
  memory(action="summarize", collections=["procedural"])
"""


@register_action(
    "memory", "summarize",
    help_text=HELP_SUMMARIZE,
    examples=[
        'memory(action="summarize")',
        'memory(action="summarize", collections=["procedural"])',
    ],
)
def run_summarize(
    collections=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Generate an LLM summary of top memories."""
    store = _mem()
    result = store.summarize(collections=collections, trace_id=trace_id)

    return ok(result, trace_id=trace_id)
