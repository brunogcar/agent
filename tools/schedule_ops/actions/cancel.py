"""tools/schedule_ops/actions/cancel.py — Cancel a scheduled job by job_id."""
from __future__ import annotations

from core.contracts import ok, fail
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "cancel",
    help_text="""cancel — Cancel a scheduled job by job_id.
Required: job_id
Optional: trace_id
Returns: {action_status: "cancelled", job_id, trace_id?}""",
    examples=['schedule(action="cancel", job_id="cron_1234567890")'],
)
def _action_cancel(job_id: str = "", trace_id: str = "", **kwargs) -> dict:
    if not job_id or not job_id.strip():
        return fail("job_id is required for cancel",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    job_id = job_id.strip()
    if job_id not in state._job_registry:
        return fail(f"No job with job_id {job_id!r}",
                    trace_id=trace_id, error_code="NOT_FOUND")

    scheduler = helpers._get_scheduler()
    if scheduler is not None:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass  # Job may have already fired / been removed — not an error.
    state._job_registry[job_id]["status"] = "cancelled"
    state._save_jobs()

    return ok({
        "action_status": "cancelled", "action": "cancel", "job_id": job_id,
        "trace_id": trace_id,
    }, trace_id=trace_id)
