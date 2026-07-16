"""tools/notify_ops/actions/recurring.py — Cron-style recurring notification. [NEW]

v1.0 introduces this action. v1.1 swaps raw CronTrigger.from_crontab() →
core.time_utils._build_cron_trigger() which remaps the DOW field to
APScheduler day-names, preserving standard cron 0=Sunday semantics
(from_crontab treats 0=Monday — a subtle trap).

Cron expression format (standard Unix cron — 0=Sunday):
    "*/5 * * * *"   — every 5 minutes
    "0 9 * * *"     — 9am daily
    "0 9 * * 1"     — 9am every Monday
    "0 0 1 * *"     — midnight on the 1st of every month
    "0 */2 * * *"   — every 2 hours on the hour

Fields (in order):
    minute (0-59), hour (0-23), day-of-month (1-31),
    month (1-12), day-of-week (0-6 where 0=Sunday)

[DESIGN] SCHEDULE TOOL INTEGRATION (v1.0+ — schedule tool has landed):
  The `schedule` tool (v1.0) now owns calendar sync, iCal/CalDAV, richer
  cron semantics, and offline missed-fire recovery. It USES notify as its
  delivery mechanism:
      schedule(action="add_cron", cron="0 9 * * *",
               delivery={"tool":"notify","action":"send","title":"...","message":"..."})
  Notify's recurring action stays focused on simple cron-style notification
  delivery; for richer scheduling (intervals, one-shots at specific times,
  calendar sync, catch-up), use the schedule tool instead.
  See the bottom of this file for the future delivery-backend roadmap.
"""
from __future__ import annotations

import time

from core.contracts import ok, fail
from core.time_utils import now, cron_next_fire, format_dt, _build_cron_trigger, get_timezone
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
        # v1.1 DOW FIX: use _build_cron_trigger (remaps DOW 0=Sunday to
        # APScheduler day-names) instead of raw from_crontab (0=Monday trap).
        trigger = _build_cron_trigger(cron, get_timezone())
    except ImportError:
        return fail(
            "APScheduler not installed. Run: pip install apscheduler",
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

        # Compute next fire time for the response payload via time_utils
        # (tz-aware, configured timezone, standard cron 0=Sunday semantics).
        next_run = cron_next_fire(cron)
        next_run_str = format_dt(next_run) if next_run else ""

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
