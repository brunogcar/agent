"""tools/notify_ops/actions/test.py — Test the delivery pipeline.

v1.0 introduces this action. Sends a known test notification through the
full _send_notification pipeline so the LLM (or a human operator) can
verify the delivery chain works end-to-end without crafting a real
notification payload.

The test notification uses fixed title="Test" and message="Notification
test successful" so it's identifiable in the delivery log (history action)
and distinguishable from real notifications.

v1.1: renamed from test_notify.py → test.py. pytest only collects from
testpaths (tests/), so there's no discovery conflict with a bare test.py
in tools/. The action_name is "test" — set by @register_action, not the
filename. Aligns with report_ops/actions/ convention.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers


_TEST_TITLE = "Test"
_TEST_MESSAGE = "Notification test successful"


@register_action(
    "notify", "test",
    help_text="""test — Send a test notification to verify the delivery pipeline works.
Optional: trace_id
Returns: {action_status: "sent", method, title, message, trace_id?}

Sends a fixed title="Test" message="Notification test successful" notification
through the full _send_notification chain. Useful for verifying that plyer /
notify-send / console fallback is wired up correctly in the current environment.
The delivery will also appear in notify(action="history") immediately after.""",
    examples=[
        'notify(action="test")',
        'notify(action="test", trace_id="smoke-1")',
    ],
)
def _action_test(trace_id: str = "", **kwargs) -> dict:
    """Send a test notification through the delivery pipeline."""
    success, method = helpers._send_notification(_TEST_TITLE, _TEST_MESSAGE)

    if not success:
        return fail(
            f"Test notification delivery failed for method={method}",
            trace_id=trace_id,
            error_code="DELIVERY_FAILED",
        )

    return ok(
        {
            "action_status": "sent",  # semantic status preserved
            "action": "test",
            "title": _TEST_TITLE,
            "message": _TEST_MESSAGE,
            "method": method,
            "trace_id": trace_id,
        },
        trace_id=trace_id,
    )
