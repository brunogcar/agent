"""tools/workflow_ops/actions/cancel.py — The `cancel` action.

Request cancellation of a running workflow by trace_id.

[DESIGN] Cancellation is workflow-specific. Currently only the autocode
workflow supports cancellation (via workflows.autocode_impl.helpers.
request_cancellation). Other workflows will complete their current step
before noticing the flag — that's documented in the response message.

If the autocode helpers module can't be imported (e.g. autocode workflow
not installed in this deployment), we still return success but note that
no cancellation mechanism is available for this deployment.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops.helpers import _make_error


@register_action(
    "workflow", "cancel",
    help_text="""cancel — Request cancellation of a running workflow by trace_id.
Required: trace_id
Returns: {status, message, trace_id} (only autocode currently supports cancellation)""",
    examples=[
        'workflow(action="cancel", trace_id="abc123")',
    ],
)
def _action_cancel(trace_id: str = "", type: str = "", **kwargs) -> dict:
    """Cancel a running workflow by trace_id."""
    if not trace_id or not trace_id.strip():
        return _make_error("trace_id is required for action='cancel'", trace_id)

    # Currently only autocode supports cancellation
    try:
        from workflows.autocode_impl.helpers import request_cancellation
        request_cancellation()
        return {
            "status": "success",
            "message": (
                f"Cancellation requested for trace_id={trace_id}. "
                "Only autocode workflow supports cancellation. "
                "Other workflows will complete their current step."
            ),
            "trace_id": trace_id,
        }
    except ImportError:
        return {
            "status": "success",
            "message": (
                f"Cancellation requested for trace_id={trace_id}, but no "
                "cancellation mechanism is available in this deployment "
                "(workflows.autocode_impl.helpers not installed)."
            ),
            "trace_id": trace_id,
        }
    except Exception as e:
        return _make_error(f"Failed to cancel: {e}", trace_id)
