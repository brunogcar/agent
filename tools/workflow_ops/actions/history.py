"""tools/workflow_ops/actions/history.py — The `history` action.

Show recent workflow runs from the tracer. Filters to traces that have a
`workflow` field or `category == "workflow"` so the response isn't polluted
with non-workflow traces (e.g. tool calls, LLM calls).

The number of recent traces returned is capped at 10 — enough to see the
last few runs without overwhelming the LLM context window.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action


@register_action(
    "workflow", "history",
    help_text="""history — Show recent workflow runs from the tracer.
No params required (optional trace_id for observability).
Returns: {status, runs: [{trace_id, workflow, goal, status, elapsed}], count, trace_id}""",
    examples=[
        'workflow(action="history")',
    ],
)
def _action_history(trace_id: str = "", **kwargs) -> dict:
    """Show recent workflow runs from the tracer."""
    try:
        from core.tracer import tracer
        recent = tracer.recent(n=10)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to read tracer history: {e}",
            "trace_id": trace_id,
        }

    # Filter to workflow-related traces (those with a "workflow" field or
    # a category of "workflow").
    workflow_runs = [
        t for t in recent
        if t.get("workflow") or t.get("category") == "workflow"
    ]

    return {
        "status": "success",
        "runs": [
            {
                "trace_id": t.get("trace_id", ""),
                "workflow": t.get("workflow", ""),
                "goal": (t.get("goal", "") or "")[:80],
                "status": t.get("status", ""),
                "elapsed": t.get("elapsed", 0),
            }
            for t in workflow_runs
        ],
        "count": len(workflow_runs),
        "trace_id": trace_id,
    }
