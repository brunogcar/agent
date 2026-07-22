"""tools/workflow_ops/actions/kill.py — The `kill` action.

Stronger than cancel. `cancel` is cooperative — it sets a flag that nodes
check between steps. `kill` is the same mechanism under the hood (Python
threads can't be force-killed mid-operation — no thread.kill() exists),
BUT it carries different intent:
  - cancel: "I changed my mind, please stop when convenient."
  - kill:   "This is stuck/hung, stop as forcefully as you can."

The response message documents the limitation: kill sets the cancellation
flag + logs the intent at warning level. The workflow stops at the next
cancellation check point (between graph nodes for non-autocode; between
LLM retries for autocode). It cannot interrupt a mid-LLM-call or
mid-subprocess operation — those complete (or time out) before the
cancellation flag is observed.

[DESIGN] Why bother with a separate action if it's the same mechanism?
  Two reasons:
  (1) Intent signaling — operators (and audit logs) can distinguish "user
      changed their mind" from "user thinks the workflow is hung." The
      kill action logs a tracer.warning, not a tracer.step.
  (2) Future escape hatch — if we ever gain the ability to actually
      force-kill (e.g. subprocess workflows, signal-based interruption),
      the kill action is the natural place to wire it in without changing
      the cancel action's cooperative semantics.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops.helpers import _make_error


@register_action(
    "workflow", "kill",
    help_text="""kill — Forcibly request termination of a running workflow by trace_id.
Required: trace_id
Returns: {status, trace_id, message} — kill sets the cancellation flag + logs the intent. Python threads cannot be force-killed mid-operation, so the workflow stops at the next cancellation check point.""",
    examples=[
        'workflow(action="kill", trace_id="abc123")',
    ],
)
def _action_kill(trace_id: str = "", **kwargs) -> dict:
    """Forcibly request termination of a running workflow by trace_id.

    Same mechanism as cancel (request_workflow_cancel) but with stronger
    intent signaling — logs a tracer.warning + returns a message that
    documents the "can't force-kill" limitation.
    """
    if not trace_id or not trace_id.strip():
        return _make_error("trace_id is required for action='kill'", trace_id)

    # 1. Set the general-purpose cancellation flag — same as cancel.
    #    run_workflow() will observe it at the next cancellation check
    #    point (post-dispatch for non-autocode; between LLM retries for
    #    autocode).
    try:
        from workflows.base import request_workflow_cancel
        request_workflow_cancel(trace_id)
    except Exception as e:
        return _make_error(f"Failed to kill: {e}", trace_id)

    # 2. Log the kill intent at WARNING level. This is the differentiator
    #    from cancel — kill signals "this is stuck," not "I changed my
    #    mind." Auditing tools can grep for warning-level kill events.
    try:
        from core.tracer import tracer
        tracer.warning(
            trace_id, "kill",
            "Kill requested — workflow will stop at the next cancellation "
            "check point (Python threads cannot be force-killed mid-operation)",
        )
    except Exception:
        # Non-fatal — the cancellation flag was already set. Don't fail
        # the kill action just because the tracer log write failed.
        pass

    return {
        "status": "success",
        "trace_id": trace_id,
        "message": (
            "Kill requested. Workflow will stop at the next cancellation "
            "check point. Python threads cannot be force-killed mid-operation."
        ),
    }
