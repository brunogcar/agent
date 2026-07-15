"""tools/notify_ops/actions/history.py — Recently sent notifications log. [NEW]

v1.0 introduces this action. Returns the last N entries from the in-memory
delivery log (state._delivery_log), which is appended to by _send_notification
after every delivery (success or fallback).

[DESIGN] WHY IN-MEMORY ONLY:
  The delivery log exists so the LLM can verify "did my last notify(action='send')
  actually deliver?". It's a debugging aid, not an audit trail. Persisting it
  would create cross-process state coupling (one process's history bleeding
  into another's) and unbounded growth concerns. The log is bounded to 50
  entries (state._MAX_DELIVERY_LOG) so long-running agents don't leak memory.

  If you need a persistent audit trail of notifications sent, that's a
  separate concern — wire up the future delivery backends (ntfy.sh / Slack /
  Discord / Telegram / email) which all have their own server-side history.
"""
from __future__ import annotations

from core.contracts import ok
from tools.notify_ops._registry import register_action
from tools.notify_ops import state


@register_action(
    "notify", "history",
    help_text="""history — Show recently sent notifications from the in-memory delivery log.
Optional: trace_id
Returns: {action_status: "ok", notifications: [...], count, total_logged, trace_id?}

Returns the last 20 delivery log entries. The full log is bounded to 50 entries
(older entries drop off the front). The log is in-memory only — it does NOT
persist across process restarts.""",
    examples=[
        'notify(action="history")',
        'notify(action="history", trace_id="audit-1")',
    ],
)
def _action_history(trace_id: str = "", **kwargs) -> dict:
    """Return the last 20 entries from the in-memory delivery log."""
    # Slice last 20 — the full log is capped at 50 by state._log_delivery().
    # We return fewer than the cap so the response payload stays small even
    # when the log is full.
    recent = state._delivery_log[-20:]
    return ok(
        {
            "action_status": "ok",  # semantic status preserved
            "action": "history",
            "notifications": recent,
            "count": len(recent),
            "total_logged": len(state._delivery_log),
            "trace_id": trace_id,
        },
        trace_id=trace_id,
    )
