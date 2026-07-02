"""Recall action — semantic search across memory collections."""
from __future__ import annotations

from core.contracts import ok, fail

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem, _validate_tags, _validate_collections

HELP_RECALL = """
recall — Semantic search across memory collections, ranked by decay score.

Parameters:
  query (required): Search query.
  top_k (default 5): Max results.
  collections: Filter to specific collections. Omit for all.
  min_score (default 0.5): Minimum decay score.
  tags_filter: Comma-separated — only return memories with ANY of these tags.
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="recall", query="how to fix syntax errors", top_k=3)
  memory(action="recall", query="ChromaDB", collections=["semantic"])
  memory(action="recall", query="tool registration", tags_filter="mcp,howto")
"""


@register_action(
    "memory", "recall",
    help_text=HELP_RECALL,
    examples=[
        'memory(action="recall", query="how to fix syntax errors", top_k=3)',
        'memory(action="recall", query="ChromaDB", collections=["semantic"])',
        'memory(action="recall", query="tool registration", tags_filter="mcp,howto")',
    ],
)
def run_recall(
    query: str = "",
    top_k: int = 5,
    collections=None,
    min_score: float = 0.5,
    tags_filter: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Search memories by semantic similarity with optional filtering."""
    if not query:
        return fail("query is required for recall", trace_id=trace_id)

    # Validate collections to prevent silent all-collections fallback on []
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    # MED-05: Validate tags_filter parameter (relaxed limit for queries)
    is_valid, err = _validate_tags(tags_filter or "", max_count=10)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    results = store.recall(
        query=query,
        top_k=top_k,
        collections=collections,
        min_score=min_score,
        tags_filter=tags_filter,
        trace_id=trace_id,
    )

    return ok({"count": len(results), "results": results}, trace_id=trace_id)
