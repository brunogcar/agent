"""tools/schedule_ops/actions/add_interval.py — Add an interval-scheduled job.

Interval = a duration string ("10m", "2h", "1d") parsed by time_utils.
Uses APScheduler IntervalTrigger.
"""
from __future__ import annotations

import time as _time

from core.contracts import ok, fail
from core.time_utils import parse_duration, now, format_dt
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "add_interval",
    help_text="""add_interval — Add an interval-scheduled recurring job (delivered via notify).
Required: interval (duration e.g. "10m"/"2h"/"1d") + (delivery dict | message)
Optional: name, title, misfire_policy (skip|fire_last|fire_all, default fire_last),
          misfire_grace (duration, default "24h"), trace_id
Returns: {action_status: "scheduled", job_id, interval, next_run, trace_id?}""",
    examples=[
        'schedule(action="add_interval", interval="10m", message="Heartbeat")',
        'schedule(action="add_interval", interval="2h", name="poll", title="Poll", message="Check status")',
    ],
)
def _action_add_interval(
    name: str = "",
    interval: str = "",
    delivery: dict = None,
    title: str = "",
    message: str = "",
    misfire_policy: str = "",
    misfire_grace: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    if not interval or not interval.strip():
        return fail('interval is required for add_interval (e.g. "10m", "2h", "1d")',
                    trace_id=trace_id, error_code="MISSING_PARAM")
    if not message and not (delivery and isinstance(delivery, dict) and delivery.get("message")):
        return fail("message (or delivery.message) is required for add_interval",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    if misfire_policy and misfire_policy not in state.VALID_MISFIRE_POLICIES:
        return fail(f"misfire_policy must be one of {sorted(state.VALID_MISFIRE_POLICIES)}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    try:
        secs = parse_duration(interval).total_seconds()
    except ValueError as e:
        return fail(f"Invalid interval {interval!r}: {e}",
                    trace_id=trace_id, error_code="INVALID_PARAM")
    if secs <= 0:
        return fail("interval must be > 0", trace_id=trace_id, error_code="INVALID_PARAM")

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail("APScheduler not installed. Run: pip install apscheduler",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    try:
        deliv = helpers._resolve_delivery(delivery, title=title, message=message, name=name)
    except ValueError as e:
        return fail(str(e), trace_id=trace_id, error_code="INVALID_PARAM")

    try:
        from apscheduler.triggers.interval import IntervalTrigger
        trigger = IntervalTrigger(seconds=secs)
    except ImportError:
        return fail("APScheduler IntervalTrigger not available.",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    job_id = f"int_{int(_time.time() * 1000)}"
    n = now()
    next_run = n + parse_duration(interval)

    try:
        scheduler.add_job(
            func=state._noop_fire,
            trigger=trigger,
            kwargs={"job_id": job_id},
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        return fail(f"Failed to add interval job: {e}",
                    trace_id=trace_id, error_code="INTERNAL_ERROR")

    state._job_registry[job_id] = {
        "name": name or deliv.get("title", "interval job"),
        "kind": "interval",
        "cron": "",
        "interval": interval,
        "run_at": "",
        "delivery": deliv,
        "misfire_policy": misfire_policy or state.DEFAULT_MISFIRE_POLICY,
        "misfire_grace": misfire_grace or state.DEFAULT_MISFIRE_GRACE,
        "fire_if_missed": False,
        "status": "recurring",
        "last_fired_at": "",
        "created_at": n.isoformat(),
        "source": "manual",
    }
    state._save_jobs()

    return ok({
        "action_status": "scheduled",
        "action": "add_interval",
        "job_id": job_id,
        "name": state._job_registry[job_id]["name"],
        "interval": interval,
        "next_run": format_dt(next_run),
        "misfire_policy": state._job_registry[job_id]["misfire_policy"],
        "misfire_grace": state._job_registry[job_id]["misfire_grace"],
        "trace_id": trace_id,
    }, trace_id=trace_id)
