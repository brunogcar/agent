"""tools/memory_ops/actions/recall_context.py — Recall context action handler.
Returns a formatted string for direct prompt injection.
NOTE: tags_filter and min_score are accepted by the facade but NOT passed to the
      backend recall_context() because the backend execute_recall_context() does
      not support these parameters. Use recall() for filtered searches.
v1.1: Added docstring documenting tags_filter/min_score limitation.
"""
from __future__ import annotations

from tools.memory_ops.helpers import _mem, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail


@register_action("memory", "recall_context", help_text="Get formatted memory context for prompt injection (query, top_k, collections)")
def run_recall_context(query: str = "", top_k: int = 5, collections=None, trace_id: str = "", **kwargs):
    if not query:
        return fail("query is required for recall_context", trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    context = store.recall_context(query=query, top_k=top_k, collections=collections, trace_id=trace_id)
    return ok({"context": context}, trace_id=trace_id)
