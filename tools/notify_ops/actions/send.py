"""tools/notify_ops/actions/send.py — Immediate notification action.

Preserves the original tools/notify.py send action behavior (cross-platform
desktop notification via _send_notification) but routes through the
notify_ops subpackage so the facade can dispatch via @meta_tool.

v1.0 changes vs. legacy send:
  - Uses ok()/fail() from core.contracts for standardized response shape.
  - trace_id threaded through the response (via ok(data, trace_id=...)).
  - Semantic status "sent" preserved in data.action_status (response.status
    is now "success" per the standardized contract).
  - Delivery automatically logged to state._delivery_log via the
    _send_notification helper (for the new `history` action).
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers


@register_action(
    "notify", "send",
    help_text="""send — Immediate desktop notification.
Required: message
Optional: title (default "Agent"), timeout (seconds, default 5), trace_id
Returns: {action_status: "sent", title, message, method, trace_id?}""",
    examples=[
        'notify(action="send", title="Research done", message="Tesla analysis complete")',
        'notify(action="send", message="Build finished", trace_id="run-42")',
    ],
)
def _action_send(
    title: str = "",
    message: str = "",
    timeout: int = 5,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Send an immediate desktop notification via plyer/notify-send/console."""
    if not message:
        return fail(
            "message is required for send",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )

    send_title = title or "Agent"
    success, method = helpers._send_notification(send_title, message, timeout)

    if not success:
        return fail(
            f"Notification delivery failed for method={method}",
            trace_id=trace_id,
            error_code="DELIVERY_FAILED",
        )

    return ok(
        {
            "action_status": "sent",  # semantic status preserved
            "action": "send",
            "title": send_title,
            "message": message,
            "method": method,
            "trace_id": trace_id,
        },
        trace_id=trace_id,
    )
