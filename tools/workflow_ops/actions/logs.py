"""tools/workflow_ops/actions/logs.py — The `logs` action.

Fetch the full step-by-step timeline for a workflow by trace_id. Goes
beyond `status` (current/last node) and `history` (recent runs) — returns
every node entry/exit + the workflow's metadata + result.

Pagination: `limit` (default 100) caps the number of steps returned.
`offset` (default 0) skips the first N steps. Use them together for paging
through long traces:
    workflow(action="logs", trace_id="abc", limit=50, offset=0)   # steps 0-49
    workflow(action="logs", trace_id="abc", limit=50, offset=50)  # steps 50-99

The response always includes `total_steps` (full count) so callers know
how many pages remain.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops.helpers import _make_error


@register_action(
    "workflow", "logs",
    help_text="""logs — Fetch the full step-by-step timeline for a workflow by trace_id.
Required: trace_id
Optional: limit (default 100, cap on steps returned), offset (default 0, skip first N steps)
Returns: {status, trace_id, workflow, goal, trace_status, started_at, elapsed_s, result, steps, total_steps, offset, limit}""",
    examples=[
        'workflow(action="logs", trace_id="abc123")',
        'workflow(action="logs", trace_id="abc123", limit=50, offset=100)',
    ],
)
def _action_logs(
    trace_id: str = "",
    limit: int = 100,
    offset: int = 0,
    **kwargs,
) -> dict:
    """Fetch the full step-by-step timeline for a workflow by trace_id."""
    if not trace_id or not trace_id.strip():
        return _make_error("trace_id is required for action='logs'", trace_id)

    # Clamp pagination params to sensible bounds.
    try:
        limit = max(0, int(limit))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        return _make_error(
            f"Invalid pagination params: limit={limit!r}, offset={offset!r}",
            trace_id,
        )

    try:
        from core.observability.reader import read_trace
    except ImportError as e:
        return _make_error(
            f"Observability reader unavailable: {e}",
            trace_id,
        )

    try:
        trace = read_trace(trace_id)
    except Exception as e:
        return _make_error(
            f"Failed to read trace {trace_id}: {e}",
            trace_id,
        )

    if not trace:
        return _make_error(f"Trace not found: {trace_id}", trace_id)

    all_steps = trace.get("steps", []) or []
    total_steps = len(all_steps)
    paged_steps = all_steps[offset:offset + limit] if limit > 0 else []

    return {
        "status": "success",
        "trace_id": trace_id,
        "workflow": trace.get("workflow"),
        "goal": trace.get("goal"),
        "trace_status": trace.get("status"),
        "started_at": trace.get("started_at"),
        "elapsed_s": trace.get("elapsed_s"),
        "result": trace.get("result"),
        "steps": paged_steps,
        "total_steps": total_steps,
        "offset": offset,
        "limit": limit,
        "trace_id_out": trace_id,
    }
