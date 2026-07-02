"""Recall context action — formatted string for direct prompt injection.

[DESIGN] This action exposes MemoryStore.recall_context() which returns a
formatted string (not a list) suitable for injecting directly into a system
prompt. It is the most useful method for agent workflows that need context
before an LLM invocation.
"""
from __future__ import annotations

from core.contracts import ok, fail

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem, _validate_collections

HELP_RECALL_CONTEXT = """
recall_context — Formatted memory context for direct prompt injection.

Returns a pre-formatted string of top memories, not a JSON list.
Use this when you need to inject memory context into a system prompt.

Parameters:
  query (required): Search query.
  top_k (default 5): Max results.
  collections: Filter to specific collections. Omit for all.
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="recall_context", query="how to fix syntax errors")
  memory(action="recall_context", query="ChromaDB", collections=["semantic"])
"""


@register_action(
    "memory", "recall_context",
    help_text=HELP_RECALL_CONTEXT,
    examples=[
        'memory(action="recall_context", query="how to fix syntax errors")',
        'memory(action="recall_context", query="ChromaDB", collections=["semantic"])',
    ],
)
def run_recall_context(
    query: str = "",
    top_k: int = 5,
    collections=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Return formatted memory context as a string."""
    if not query:
        return fail("query is required for recall_context", trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    context = store.recall_context(
        query=query,
        top_k=top_k,
        collections=collections,
        trace_id=trace_id,
    )

    return ok({"context": context}, trace_id=trace_id)
