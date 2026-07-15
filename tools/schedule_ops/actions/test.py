"""tools/schedule_ops/actions/test.py — Fire a test delivery immediately.

Verifies the schedule→notify delivery pipeline end-to-end without scheduling
a job. Useful for confirming notify is reachable + configured before relying
on scheduled fires.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "test",
    help_text="""test — Fire a test delivery immediately via notify (no job scheduled).
Optional: title (default "Schedule test"), message (default "Schedule delivery test"), trace_id
Returns: {action_status: "ok", delivery_result, trace_id?}""",
    examples=['schedule(action="test")', 'schedule(action="test", title="Ping", message="hello")'],
)
def _action_test(
    title: str = "",
    message: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    t = title or "Schedule test"
    m = message or "Schedule delivery test"
    try:
        deliv = helpers._resolve_delivery(None, title=t, message=m, name="test")
    except ValueError as e:
        return fail(str(e), trace_id=trace_id, error_code="INVALID_PARAM")
    result = helpers._call_notify(deliv)
    try:
        state._log_delivery("(test)", _now(), deliv, result, False, trace_id)
    except Exception:
        pass
    return ok({
        "action_status": "ok", "action": "test",
        "delivery_result": result, "trace_id": trace_id,
    }, trace_id=trace_id)


def _now():
    from core.time_utils import now
    return now()
