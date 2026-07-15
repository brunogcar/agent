"""tools/schedule_ops/actions/add_cron.py — Add a cron-scheduled job.

Uses core.time_utils._build_cron_trigger (standard cron 0=Sunday semantics,
DOW remapped to APScheduler day-names) so "0 9 * * 1" means 09:00 every
Monday — NOT Tuesday (APScheduler's raw from_crontab treats 0=Monday, a
subtle trap that time_utils fixes).
"""
from __future__ import annotations

import time as _time

from core.contracts import ok, fail
from core.time_utils import cron_next_fire, format_dt, get_timezone, _build_cron_trigger
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "add_cron",
    help_text="""add_cron — Add a cron-scheduled recurring job (delivered via notify).
Required: cron (5-field, 0=Sunday) + (delivery dict | message)
Optional: name, title, misfire_policy (skip|fire_last|fire_all, default fire_last),
          misfire_grace (duration e.g. "24h", default "24h"), trace_id
Returns: {action_status: "scheduled", job_id, cron, next_run, trace_id?}""",
    examples=[
        'schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="Daily standup")',
        'schedule(action="add_cron", cron="0 9 * * 1", name="weekly_report", message="Mon report", misfire_policy="fire_all")',
    ],
)
def _action_add_cron(
    name: str = "",
    cron: str = "",
    delivery: dict = None,
    title: str = "",
    message: str = "",
    misfire_policy: str = "",
    misfire_grace: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    if not cron or not cron.strip():
        return fail("cron is required for add_cron (e.g. '0 9 * * *' = 9am daily)",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    cron = cron.strip()
    if not message and not (delivery and isinstance(delivery, dict) and delivery.get("message")):
        return fail("message (or delivery.message) is required for add_cron",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    if misfire_policy and misfire_policy not in state.VALID_MISFIRE_POLICIES:
        return fail(f"misfire_policy must be one of {sorted(state.VALID_MISFIRE_POLICIES)}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail("APScheduler not installed. Run: pip install apscheduler",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    # Validate cron + build trigger (raises ValueError on bad expr / DOW).
    try:
        trigger = _build_cron_trigger(cron, get_timezone())
    except Exception as e:
        return fail(f"Invalid cron expression {cron!r}: {e}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    try:
        deliv = helpers._resolve_delivery(delivery, title=title, message=message, name=name)
    except ValueError as e:
        return fail(str(e), trace_id=trace_id, error_code="INVALID_PARAM")

    job_id = f"cron_{int(_time.time() * 1000)}"
    next_run = cron_next_fire(cron)

    try:
        scheduler.add_job(
            func=state._noop_fire,
            trigger=trigger,
            kwargs={"job_id": job_id},
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        return fail(f"Failed to add cron job: {e}",
                    trace_id=trace_id, error_code="INTERNAL_ERROR")

    state._job_registry[job_id] = {
        "name": name or deliv.get("title", "cron job"),
        "kind": "cron",
        "cron": cron,
        "interval": "",
        "run_at": "",
        "delivery": deliv,
        "misfire_policy": misfire_policy or state.DEFAULT_MISFIRE_POLICY,
        "misfire_grace": misfire_grace or state.DEFAULT_MISFIRE_GRACE,
        "fire_if_missed": False,
        "status": "recurring",
        "last_fired_at": "",
        "created_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "manual",
    }
    state._save_jobs()

    return ok({
        "action_status": "scheduled",
        "action": "add_cron",
        "job_id": job_id,
        "name": state._job_registry[job_id]["name"],
        "cron": cron,
        "next_run": format_dt(next_run) if next_run else "",
        "misfire_policy": state._job_registry[job_id]["misfire_policy"],
        "misfire_grace": state._job_registry[job_id]["misfire_grace"],
        "trace_id": trace_id,
    }, trace_id=trace_id)
