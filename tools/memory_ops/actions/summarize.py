"""tools/memory_ops/actions/summarize.py — Summarize action handler.
v1.1: Added collections validation, pass trace_id to backend.
"""
from __future__ import annotations

from tools.memory_ops.helpers import _mem, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail


@register_action("memory", "summarize", help_text="Summarize top memories across collections")
def run_summarize(collections=None, trace_id: str = "", **kwargs):
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    result = store.summarize(collections=collections, trace_id=trace_id)
    return ok(result, trace_id=trace_id)
