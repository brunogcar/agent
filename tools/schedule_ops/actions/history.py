"""tools/schedule_ops/actions/history.py — Recent schedule deliveries (in-memory log)."""
from __future__ import annotations

from core.contracts import ok
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import state


@register_action(
    "schedule", "history",
    help_text="""history — Show recent schedule deliveries (in-memory, last N).
Optional: limit (int, default 20, max 100), trace_id
Returns: {action_status: "ok", deliveries: [...], count, trace_id?}""",
    examples=['schedule(action="history")', 'schedule(action="history", limit=5)'],
)
def _action_history(limit: int = 20, trace_id: str = "", **kwargs) -> dict:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    if limit < 1:
        limit = 20
    if limit > 100:
        limit = 100
    # Most-recent first.
    deliveries = list(reversed(state._delivery_log))[:limit]
    return ok({
        "action_status": "ok", "action": "history",
        "deliveries": deliveries, "count": len(deliveries),
        "trace_id": trace_id,
    }, trace_id=trace_id)
