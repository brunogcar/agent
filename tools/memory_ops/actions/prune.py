"""tools/memory_ops/actions/prune.py — Prune action handler.
v1.1: Added collections validation, max_age_days/min_importance range checks.
"""
from __future__ import annotations

from tools.memory_ops.helpers import _mem, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail


@register_action("memory", "prune", help_text="Remove stale or low-importance memories")
def run_prune(max_age_days=30, min_importance=3, dry_run=True, collections=None, trace_id: str = "", **kwargs):
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    if max_age_days < 0:
        return fail("max_age_days must be >= 0", trace_id=trace_id)
    if min_importance < 1 or min_importance > 10:
        return fail("min_importance must be 1-10", trace_id=trace_id)

    store = _mem()
    result = store.prune(
        max_age_days=max_age_days,
        min_importance=min_importance,
        dry_run=dry_run,
        collections=collections,
    )
    return ok(result, trace_id=trace_id)
