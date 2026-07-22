"""tools/workflow_ops/actions/resume.py — The `resume` action.

Resume an interrupted workflow by trace_id, OR list incomplete workflows
when no trace_id is given. Cleaner API than `run` with `resume=True` because
the caller doesn't need to know the workflow type — the resume action reads
it from the checkpoint.

Two modes:
  1. workflow(action="resume", trace_id="abc123")
       - Read the checkpoint via get_latest(trace_id).
       - Extract `workflow` type + `goal` from the checkpoint state.
       - Forward to run_workflow(workflow_type=..., goal=..., trace_id=...,
         resume=True, **checkpoint_overrides).
       - checkpoint_overrides = all non-control fields from the checkpoint
         state (project_root, target_file, mode, etc. — everything except
         status/error/result/messages/trace_id).

  2. workflow(action="resume")
       - Call scan_incomplete() to list trace_ids with non-terminal status.
       - For each trace_id, call get_latest() to get the workflow type +
         goal + last node.
       - Return {status: "success", incomplete: [...], count: N}.

[DESIGN] Why a separate action instead of `run(resume=True)`?
  The `run` action requires `type` (workflow type) — but on resume, the
  type is already stored in the checkpoint. Forcing the caller to re-specify
  it is friction + a footgun (what if they specify the wrong type?). The
  resume action reads the type FROM the checkpoint, so the caller only
  needs to pass trace_id.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops._type_registry import TYPE_DISPATCH
from tools.workflow_ops.helpers import _make_error


# Control fields that should NOT be forwarded as checkpoint_overrides to
# run_workflow. These are either internal bookkeeping (status, error,
# result, messages, _checkpoint_version) or already passed explicitly
# (trace_id, workflow type, goal).
_CONTROL_FIELDS = frozenset({
    "status",
    "error",
    "errors",
    "result",
    "messages",
    "trace_id",
    "workflow",
    "goal",
    "task",
    "_checkpoint_node",
    "_checkpoint_version",
    "resume_count",
    "duration_ms",
    "artifacts",
})


@register_action(
    "workflow", "resume",
    help_text="""resume — Resume an interrupted workflow by trace_id, OR list incomplete workflows.
Required (mode 1): trace_id — resumes that specific workflow.
Required (mode 2): no params — lists all incomplete workflows from the checkpoint journal.
Returns (mode 1): the resumed workflow's result dict.
Returns (mode 2): {status, incomplete: [{trace_id, workflow, goal, last_node, status}], count}""",
    examples=[
        'workflow(action="resume", trace_id="abc123")',
        'workflow(action="resume")',
    ],
)
def _action_resume(trace_id: str = "", **kwargs) -> dict:
    """Resume a workflow by trace_id, or list incomplete workflows."""
    # ── Mode 2: no trace_id → list incomplete workflows ──────────────────
    if not trace_id or not trace_id.strip():
        try:
            from core.observability.checkpoint import scan_incomplete, get_latest
        except ImportError as e:
            return _make_error(
                f"Checkpoint module unavailable: {e}",
                trace_id,
            )

        try:
            incomplete_ids = scan_incomplete()
        except Exception as e:
            return _make_error(
                f"Failed to scan incomplete workflows: {e}",
                trace_id,
            )

        if not incomplete_ids:
            return {
                "status": "success",
                "incomplete": [],
                "count": 0,
                "message": "No incomplete workflows found",
                "trace_id": trace_id,
            }

        incomplete = []
        for tid in incomplete_ids:
            try:
                cp = get_latest(tid)
            except Exception:
                cp = None
            if not cp:
                # Checkpoint may have been deleted between scan + read
                # (race) — skip it.
                continue
            incomplete.append({
                "trace_id": tid,
                "workflow": cp.get("workflow", ""),
                "goal": (cp.get("goal", "") or "")[:80],
                "last_node": cp.get("_checkpoint_node", ""),
                "status": cp.get("status", ""),
            })

        return {
            "status": "success",
            "incomplete": incomplete,
            "count": len(incomplete),
            "trace_id": trace_id,
        }

    # ── Mode 1: trace_id given → resume that specific workflow ───────────
    try:
        from core.observability.checkpoint import get_latest
    except ImportError as e:
        return _make_error(
            f"Checkpoint module unavailable: {e}",
            trace_id,
        )

    try:
        checkpoint = get_latest(trace_id)
    except Exception as e:
        return _make_error(
            f"Failed to read checkpoint for trace_id={trace_id}: {e}",
            trace_id,
        )

    if not checkpoint:
        return _make_error(
            f"No checkpoint found for trace_id={trace_id}",
            trace_id,
        )

    wf_type = checkpoint.get("workflow", "")
    if not wf_type:
        return _make_error(
            f"Checkpoint for trace_id={trace_id} has no 'workflow' field — "
            "cannot determine workflow type to resume",
            trace_id,
        )

    if wf_type not in TYPE_DISPATCH:
        return _make_error(
            f"Checkpoint workflow type '{wf_type}' is not registered in "
            f"TYPE_DISPATCH. Valid: {sorted(TYPE_DISPATCH.keys())}",
            trace_id,
            valid_types=sorted(TYPE_DISPATCH.keys()),
        )

    goal = checkpoint.get("goal", "") or ""

    # Extract non-control fields to forward as overrides. These are the
    # params the original run was invoked with (target_file, project_root,
    # mode, error_msg, etc.) — preserved in the checkpoint state.
    overrides = {
        k: v for k, v in checkpoint.items()
        if k not in _CONTROL_FIELDS and v is not None and v != ""
    }

    # Forward to the type handler (same path as `run` action). The type
    # handler will call _execute_workflow() → run_workflow(resume=True).
    type_handler = TYPE_DISPATCH[wf_type]["func"]
    return type_handler(
        goal=goal,
        trace_id=trace_id,
        resume=True,
        **overrides,
    )
