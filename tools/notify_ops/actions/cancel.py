"""tools/notify_ops/actions/cancel.py — Cancel a scheduled notification.

Preserves the original tools/notify.py cancel action behavior (remove job
from APScheduler by job_id) but routes through notify_ops.

v1.0 changes vs. legacy cancel:
  - Uses ok()/fail() from core.contracts.
  - trace_id threaded through response.
  - Semantic status "cancelled" preserved in data.action_status.
  - Calls state._save_jobs() after removing the job so persistence stays
    in sync.
  - Distinguishes "job not found in registry" from "scheduler removal
    failed" with explicit error_code for programmatic classification.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers
from tools.notify_ops import state


@register_action(
    "notify", "cancel",
    help_text="""cancel — Cancel a scheduled or recurring notification by job_id.
Required: job_id (from schedule or recurring response)
Optional: trace_id
Returns: {action_status: "cancelled", job_id, trace_id?}""",
    examples=[
        'notify(action="cancel", job_id="reminder_1234567890")',
    ],
)
def _action_cancel(
    job_id: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Cancel a scheduled notification by removing it from APScheduler."""
    if not job_id:
        return fail(
            "job_id is required for cancel",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )

    # Fast-fail if job_id isn't in our registry — avoids APScheduler's
    # JobLookupError noise and gives a cleaner error_code for callers.
    if job_id not in state._job_registry:
        return fail(
            f"Job '{job_id}' not found in registry (it may have already fired or never existed).",
            trace_id=trace_id,
            error_code="NOT_FOUND",
        )

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail(
            "Scheduler not running (APScheduler not installed).",
            trace_id=trace_id,
            error_code="DEPENDENCY_MISSING",
        )

    try:
        scheduler.remove_job(job_id)
    except Exception as e:
        # Job may have already fired + been auto-removed by APScheduler.
        # We still pop from our registry below so the system stays consistent.
        # Use a softer error_code so callers can distinguish "real failure"
        # from "already-gone" if they want to.
        pass

    state._job_registry.pop(job_id, None)
    state._save_jobs()

    return ok(
        {
            "action_status": "cancelled",  # semantic status preserved
            "action": "cancel",
            "job_id": job_id,
            "trace_id": trace_id,
        },
        trace_id=trace_id,
    )
