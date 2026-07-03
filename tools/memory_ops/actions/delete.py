"""tools/memory_ops/actions/delete.py — Delete action handler.
v1.1: Added collections validation, confirm_ids optional, threshold fix, trace_id pass-through.
"""
from __future__ import annotations

from tools.memory_ops.helpers import _mem, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail


@register_action("memory", "delete", help_text="Remove memories by query or explicit IDs")
def run_delete(query: str = "", collections=None, threshold=0.0, confirm_ids=None, trace_id: str = "", **kwargs):
    if not query and not confirm_ids:
        return fail("query or confirm_ids is required for delete", trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    result = store.delete(
        query=query, collections=collections,
        threshold=threshold if threshold is not None else None,
        confirm_ids=confirm_ids,
    )
    return ok(result, trace_id=trace_id)
