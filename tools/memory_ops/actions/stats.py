"""Stats action — return collection statistics without loading vectors."""
from __future__ import annotations

from core.contracts import ok

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem

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
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Return collection statistics."""
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
