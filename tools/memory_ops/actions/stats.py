"""Stats action — return collection statistics without loading vectors.
v1.2: Added collections validation for consistency with other actions.
"""
from __future__ import annotations

from core.contracts import ok, fail

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem, _validate_collections

HELP_STATS = """
stats — Return counts for all collections without loading ChromaDB vectors.

Parameters:
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="stats")
"""

@register_action(
    "memory", "stats",
    help_text=HELP_STATS,
    examples=[
        'memory(action="stats")',
    ],
)
def run_stats(
    collections=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Return collection statistics."""
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    raw = store.stats()
    # Handle both nested dicts {"episodic": {"count": N}} and flat {"episodic": N}
    total = 0
    for v in raw.values():
        if isinstance(v, dict):
            total += v.get("count", 0)
        elif isinstance(v, (int, float)):
            total += v

    return ok({"collections": raw, "total": total}, trace_id=trace_id)
