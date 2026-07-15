"""tools/notify_ops/actions/recurring.py — Cron-style recurring notification. [NEW]

v1.0 introduces this action. Uses APScheduler CronTrigger.from_crontab() to
parse a standard 5-field cron expression and schedule a recurring job.

Cron expression format (standard Unix cron — APScheduler's from_crontab
matches the vixie-cron semantics):
    "*/5 * * * *"   — every 5 minutes
    "0 9 * * *"     — 9am daily
    "0 9 * * 1"     — 9am every Monday
    "0 0 1 * *"     — midnight on the 1st of every month
    "0 */2 * * *"   — every 2 hours on the hour

Fields (in order):
    minute (0-59), hour (0-23), day-of-month (1-31),
    month (1-12), day-of-week (0-6 where 0=Sunday)

[DESIGN] FUTURE INTEGRATION — schedule tool:
  A future `schedule` tool will own calendar sync, iCal/CalDAV, and richer
  cron semantics (CRON_TZ, human-readable "every weekday" parsing, etc.).
  That schedule tool will USE notify as its delivery mechanism:
      schedule(action="add_cron", cron="0 9 * * *",
               delivery=notify(action="send", title="Standup", message="..."))
  Notify's recurring action stays focused on the notification delivery use
  case; richer scheduling logic moves to the schedule tool when it lands.
  See the bottom of this file for the future delivery-backend roadmap.
"""
from __future__ import annotations

import time
from datetime import datetime

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import helpers
from tools.notify_ops import state


@register_action(
    "notify", "recurring",
    help_text="""recurring — Schedule a cron-style recurring notification.
Required: message, cron (5-field cron expression)
Optional: title (default "Agent Reminder"), trace_id
Returns: {action_status: "scheduled", job_id, cron, next_run, trace_id?}

Cron format: "minute hour day-of-month month day-of-week"
Examples:
  "*/5 * * * *"   every 5 minutes
  "0 9 * * *"     9am daily
  "0 9 * * 1"     9am every Monday
  "0 0 1 * *"     midnight on the 1st of every month""",
    examples=[
        'notify(action="recurring", cron="0 9 * * *", title="Standup", message="Daily standup time")',
        'notify(action="recurring", cron="*/15 * * * *", message="Heartbeat")',
    ],
)
def _action_recurring(
    title: str = "",
    message: str = "",
    cron: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Schedule a recurring notification via APScheduler CronTrigger."""
    if not message:
        return fail(
            "message is required for recurring",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )
    if not cron or not cron.strip():
        return fail(
            "cron is required for recurring (e.g. '0 9 * * *' = 9am daily)",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )

    cron = cron.strip()

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail(
            "APScheduler not installed. Run: pip install apscheduler",
            trace_id=trace_id,
            error_code="DEPENDENCY_MISSING",
        )

    # Validate the cron expression by parsing it BEFORE adding the job.
    # APScheduler raises ValueError on invalid expressions — we catch it
    # here to produce a clean fail() response with INVALID_PARAM error_code
    # rather than letting it bubble up as INTERNAL_ERROR.
    try:
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger.from_crontab(cron)
    except ImportError:
        return fail(
            "APScheduler CronTrigger not available. Run: pip install apscheduler",
            trace_id=trace_id,
            error_code="DEPENDENCY_MISSING",
        )
    except Exception as e:
        return fail(
            f"Invalid cron expression {cron!r}: {e}",
            trace_id=trace_id,
            error_code="INVALID_PARAM",
        )

    try:
        job_id = f"recurring_{int(time.time())}"
        send_title = title or "Agent Reminder"

        scheduler.add_job(
            func=helpers._send_notification,
            trigger=trigger,
            kwargs={"title": send_title, "message": message},
            id=job_id,
        )

        # Compute next fire time for the response payload. APScheduler's
        # CronTrigger.get_next_fire_time() takes (previous_fire_time, now)
        # — pass None for previous to get the next upcoming fire.
        next_run = trigger.get_next_fire_time(None, datetime.now())
        next_run_str = next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else ""

        state._job_registry[job_id] = {
            "title": send_title,
            "message": message,
            "run_at": "",  # Not applicable for CronTrigger jobs.
            "cron": cron,
            "status": "recurring",
            "recurring": True,
        }
        state._save_jobs()

        return ok(
            {
                "action_status": "scheduled",  # semantic status preserved
                "action": "recurring",
                "job_id": job_id,
                "cron": cron,
                "next_run": next_run_str,
                "title": send_title,
                "message": message,
                "trace_id": trace_id,
            },
            trace_id=trace_id,
        )
    except Exception as e:
        return fail(
            f"Recurring schedule failed: {e}",
            trace_id=trace_id,
            error_code="INTERNAL_ERROR",
        )


# ── FUTURE DELIVERY BACKENDS (not yet implemented) ───────────────────────────
# The current implementation only supports local desktop notifications
# (plyer / notify-send / console). Future delivery backends will be added
# either as new actions or as gateway integrations that notify delegates to:
#
#   - ntfy.sh    (self-hosted Docker push service; HTTP POST → push to phone)
#   - Slack      (incoming webhook; channel-scoped notification)
#   - Discord    (incoming webhook; bot-channel notification)
#   - Telegram   (Bot API; chat_id-scoped notification)
#   - Email      (SMTP; recipient-scoped notification)
#
# Proposed API extension (v2.0+):
#   notify(action="send", title="...", message="...",
#           backend="ntfy", backend_config={"topic": "agent-alerts"})
#
# When the schedule tool lands, the `backend` param will likely move to the
# schedule tool's ownership — notify's job is "deliver via the configured
# channel", not "decide which channel".
