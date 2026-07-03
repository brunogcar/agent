"""tools/memory_ops/actions/store.py — Store action handler.
v1.1: Removed dead compress_result import. Use helpers.cfg for mock propagation.
"""
from __future__ import annotations

from tools.memory_ops import helpers
from tools.memory_ops.helpers import _mem, _validate_tags, _validate_memory_type, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail


@register_action("memory", "store", help_text="Save a memory (text, memory_type, importance, tags, goal, outcome, tools_used, source)")
def run_store(text="", memory_type="", tags="", collections=None, importance=5, trace_id="", goal="", outcome="", tools_used="", source="", **kwargs):
    if not text:
        return fail("text is required for store", trace_id=trace_id)

    is_valid, err = _validate_tags(tags, max_count=helpers.cfg.max_tags_per_entry)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    is_valid, err = _validate_memory_type(memory_type)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    text_bytes = len(text.encode("utf-8"))
    if text_bytes > helpers.cfg.memory_max_entry_bytes:
        return fail(
            f"text is {text_bytes} bytes — exceeds limit of {helpers.cfg.memory_max_entry_bytes}",
            trace_id=trace_id,
        )

    if importance < 1 or importance > 10:
        return fail(f"importance must be 1-10, got {importance}", trace_id=trace_id)

    store = _mem()
    result = store.store(
        text=text, memory_type=memory_type, importance=importance,
        tags=tags, trace_id=trace_id, goal=goal, outcome=outcome,
        tools_used=tools_used, source=source,
    )
    return ok(result, trace_id=trace_id)
