"""tools/workflow_ops/actions/status.py — The `status` action.

Check the status of a workflow by trace_id. Looks up both:
  - The checkpoint journal (core/observability/checkpoint.get_latest)
  - The tracer (core.tracer.tracer.summary)

Returns both pieces so the caller can see whether the workflow reached a
checkpoint and what the tracer recorded.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops.helpers import _make_error


@register_action(
    "workflow", "status",
    help_text="""status — Check the status of a workflow by trace_id.
Required: trace_id
Returns: {status, trace_id, checkpoint, checkpoint_node, checkpoint_status, tracer_summary}""",
    examples=[
        'workflow(action="status", trace_id="abc123")',
    ],
)
def _action_status(trace_id: str = "", **kwargs) -> dict:
    """Check status of a workflow by trace_id."""
    if not trace_id or not trace_id.strip():
        return _make_error("trace_id is required for action='status'", trace_id)

    # Check checkpoint journal
    checkpoint = None
    try:
        from core.observability.checkpoint import get_latest
        checkpoint = get_latest(trace_id)
    except Exception:
        # checkpoint module may not be available in all deployments
        checkpoint = None

    # Check tracer for the trace
    summary = None
    try:
        from core.tracer import tracer
        summary = tracer.summary(trace_id)
    except Exception:
        summary = None

    return {
        "status": "success",
        "trace_id": trace_id,
        "checkpoint": checkpoint is not None,
        "checkpoint_node": checkpoint.get("_checkpoint_node", "") if checkpoint else "",
        "checkpoint_status": checkpoint.get("status", "") if checkpoint else "",
        "tracer_summary": summary,
    }
