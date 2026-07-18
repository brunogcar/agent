"""tools/workflow_ops/actions/cancel.py — The `cancel` action.

Request cancellation of a running workflow by trace_id.

[DESIGN] Cancellation now works for ALL workflows (v1.1-p1):
  1. request_workflow_cancel(trace_id) — sets a per-trace_id flag in
     workflows.base that run_workflow() checks AFTER the dispatch returns.
     For non-autocode workflows, this is post-hoc — graph.invoke() is
     blocking, so the cancel takes effect after the current step completes.
  2. request_cancellation() — the legacy autocode-specific flag (no args).
     Autocode's _call() checks this between retries, enabling mid-execution
     interrupt (e.g. interrupting a long LLM backoff sleep).

Both flags are set on every cancel call. The response message documents
the difference: autocode interrupts mid-execution; other workflows finish
their current step first.

If the autocode helpers module can't be imported (e.g. autocode workflow
not installed in this deployment), we still set the general-purpose flag
and return success — non-autocode workflows can still be cancelled.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops.helpers import _make_error


@register_action(
    "workflow", "cancel",
    help_text="""cancel — Request cancellation of a running workflow by trace_id.
Required: trace_id
Returns: {status, message, trace_id, autocode_cancelled} (all workflows support cancellation; autocode interrupts mid-execution, others finish their current step)""",
    examples=[
        'workflow(action="cancel", trace_id="abc123")',
    ],
)
def _action_cancel(trace_id: str = "", type: str = "", **kwargs) -> dict:
    """Cancel a running workflow by trace_id.

    Sets BOTH cancellation flags:
      - request_workflow_cancel(trace_id): general-purpose, checked by
        run_workflow() after dispatch returns (all workflows).
      - request_cancellation(): autocode-specific, checked by _call()
        between retries (autocode only — mid-execution interrupt).
    """
    if not trace_id or not trace_id.strip():
        return _make_error("trace_id is required for action='cancel'", trace_id)

    # 1. General-purpose flag — works for ALL workflows. run_workflow()
    #    checks is_workflow_cancelled(trace_id) after the dispatch returns.
    try:
        from workflows.base import request_workflow_cancel
        request_workflow_cancel(trace_id)
    except Exception as e:
        return _make_error(f"Failed to cancel: {e}", trace_id)

    # 2. Autocode-specific flag — enables mid-execution interrupt for
    #    autocode (the _call() retry loop checks this between attempts).
    #    If autocode isn't installed in this deployment, the general-purpose
    #    flag above still works for non-autocode workflows.
    autocode_cancelled = False
    try:
        from workflows.autocode_impl.helpers import request_cancellation
        request_cancellation()
        autocode_cancelled = True
    except ImportError:
        # autocode module not installed — non-fatal. General-purpose flag
        # is already set, so non-autocode workflows can still be cancelled.
        pass
    except Exception as e:
        return _make_error(f"Failed to cancel: {e}", trace_id)

    return {
        "status": "success",
        "message": (
            f"Cancellation requested for trace_id={trace_id}. "
            "Autocode interrupts mid-execution; other workflows "
            "finish their current step before noticing the flag."
        ),
        "trace_id": trace_id,
        "autocode_cancelled": autocode_cancelled,
    }
