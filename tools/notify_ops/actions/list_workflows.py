"""tools/notify_ops/actions/list_workflows.py — List scheduled notifications.

The action_name is "list" but the module is named list_workflows.py to
mirror the naming convention used by other tools (workflow_ops/actions/
list_workflows.py). The auto-discovery in notify_ops/__init__.py globs
*.py and imports them — the actual action_name registered via
@register_action is what @meta_tool reads for the Literal enum.

Preserves the original tools/notify.py list action behavior (query
APScheduler for all jobs + enrich with registry metadata) but routes
through notify_ops.

v1.0 changes vs. legacy list:
  - Uses ok()/fail() from core.contracts.
  - trace_id threaded through response.
  - Semantic status "ok" preserved in data.action_status.
  - When scheduler is None, returns empty list with a note (not an error)
    so callers can call list() defensively without conditional logic.
  - Adds "recurring" + "cron" fields per job so callers can distinguish
    one-shot DateTrigger jobs from recurring CronTrigger jobs.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers
from tools.notify_ops import state


@register_action(
    "notify", "list",
    help_text="""list — List all scheduled and recurring notifications.
Optional: trace_id
Returns: {action_status: "ok", jobs: [{job_id, run_at, title, message, recurring, cron?}], count, note?}""",
    examples=[
        'notify(action="list")',
    ],
)
def _action_list(trace_id: str = "", **kwargs) -> dict:
    """List all scheduled notifications from APScheduler + registry metadata."""
    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return ok(
            {
                "action_status": "ok",
                "action": "list",
                "jobs": [],
                "count": 0,
                "note": "Scheduler not running (APScheduler not installed).",
                "trace_id": trace_id,
            },
            trace_id=trace_id,
        )

    try:
        jobs = scheduler.get_jobs()
        result = []
        for job in jobs:
            meta = state._job_registry.get(job.id, {})
            entry = {
                "job_id": job.id,
                "run_at": str(job.next_run_time) if job.next_run_time else "",
                "title": meta.get("title", ""),
                "message": meta.get("message", ""),
                "recurring": meta.get("recurring", False),
            }
            if meta.get("recurring"):
                entry["cron"] = meta.get("cron", "")
            result.append(entry)
        return ok(
            {
                "action_status": "ok",  # semantic status preserved
                "action": "list",
                "jobs": result,
                "count": len(result),
                "trace_id": trace_id,
            },
            trace_id=trace_id,
        )
    except Exception as e:
        return fail(
            f"List failed: {e}",
            trace_id=trace_id,
            error_code="INTERNAL_ERROR",
        )
