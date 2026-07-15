"""tools/notify_ops/actions/schedule.py — Schedule one-shot notification.

Preserves the original tools/notify.py schedule action behavior (APScheduler
DateTrigger after N minutes) but routes through notify_ops.

v1.0 changes vs. legacy schedule:
  - Uses ok()/fail() from core.contracts.
  - trace_id threaded through response.
  - Semantic status "scheduled" preserved in data.action_status.
  - Calls state._save_jobs() after registering the job so the schedule
    survives process restarts.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers
from tools.notify_ops import state


@register_action(
    "notify", "schedule",
    help_text="""schedule — Schedule a one-shot notification N minutes from now.
Required: message, delay_minutes (>0)
Optional: title (default "Agent Reminder"), trace_id
Returns: {action_status: "scheduled", job_id, run_at, delay_minutes, trace_id?}""",
    examples=[
        'notify(action="schedule", message="Check autocode results", delay_minutes=10)',
        'notify(action="schedule", title="Standup", message="9am standup", delay_minutes=60, trace_id="d-1")',
    ],
)
def _action_schedule(
    title: str = "",
    message: str = "",
    delay_minutes: int = 0,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Schedule a notification N minutes in the future via APScheduler DateTrigger."""
    if not message:
        return fail(
            "message is required for schedule",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )
    if delay_minutes <= 0:
        return fail(
            "delay_minutes must be > 0 for schedule",
            trace_id=trace_id,
            error_code="INVALID_PARAM",
        )

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail(
            "APScheduler not installed. Run: pip install apscheduler",
            trace_id=trace_id,
            error_code="DEPENDENCY_MISSING",
        )

    try:
        from apscheduler.triggers.date import DateTrigger

        run_time = datetime.now() + timedelta(minutes=delay_minutes)
        job_id = f"reminder_{int(time.time())}"
        send_title = title or "Agent Reminder"

        # The job calls the canonical _send_notification (which logs delivery).
        # We pass title/message as kwargs so APScheduler can fire it without
        # needing closure capture (cleaner shutdown semantics).
        scheduler.add_job(
            func=helpers._send_notification,
            trigger=DateTrigger(run_date=run_time),
            kwargs={"title": send_title, "message": message},
            id=job_id,
        )

        state._job_registry[job_id] = {
            "title": send_title,
            "message": message,
            "run_at": run_time.isoformat(),
            "cron": "",
            "status": "scheduled",
            "recurring": False,
        }
        state._save_jobs()

        return ok(
            {
                "action_status": "scheduled",  # semantic status preserved
                "action": "schedule",
                "job_id": job_id,
                "message": message,
                "run_at": run_time.strftime("%Y-%m-%d %H:%M:%S"),
                "delay_minutes": delay_minutes,
                "trace_id": trace_id,
            },
            trace_id=trace_id,
        )
    except Exception as e:
        return fail(
            f"Schedule failed: {e}",
            trace_id=trace_id,
            error_code="INTERNAL_ERROR",
        )
