"""tools/schedule_ops/actions/add_once.py — Add a one-shot job (fire once at run_at).

run_at is parsed by time_utils.parse_human (ISO, "in 10m", "9am", "tomorrow",
"2026-07-16 09:00"). Uses APScheduler DateTrigger.
"""
from __future__ import annotations

import time as _time

from core.contracts import ok, fail
from core.time_utils import parse_human, parse_iso, now, format_dt
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "add_once",
    help_text="""add_once — Add a one-shot job that fires once at run_at (delivered via notify).
Required: run_at (ISO | "in 10m" | "9am" | "2026-07-16 09:00") + (delivery dict | message)
Optional: name, title, fire_if_missed (bool, default false — if true and run_at
          passed while offline, fire once on next boot within grace),
          misfire_grace (duration, default "24h"), trace_id
Returns: {action_status: "scheduled", job_id, run_at, trace_id?}""",
    examples=[
        'schedule(action="add_once", run_at="in 30m", message="Coffee break")',
        'schedule(action="add_once", run_at="2026-07-16T09:00:00", title="Meeting", message="Standup", fire_if_missed=true)',
    ],
)
def _action_add_once(
    name: str = "",
    run_at: str = "",
    delivery: dict = None,
    title: str = "",
    message: str = "",
    fire_if_missed: bool = False,
    misfire_grace: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    if not run_at or not run_at.strip():
        return fail('run_at is required for add_once (e.g. "in 30m", "9am", "2026-07-16T09:00:00")',
                    trace_id=trace_id, error_code="MISSING_PARAM")
    if not message and not (delivery and isinstance(delivery, dict) and delivery.get("message")):
        return fail("message (or delivery.message) is required for add_once",
                    trace_id=trace_id, error_code="MISSING_PARAM")

    try:
        target = parse_human(run_at)
    except ValueError as e:
        return fail(f"Invalid run_at {run_at!r}: {e}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    n = now()
    if target <= n:
        return fail(f"run_at {format_dt(target)} is in the past (now={format_dt(n)}). "
                    f"Use a future time, or notify(action='send') for immediate delivery.",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail("APScheduler not installed. Run: pip install apscheduler",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    try:
        deliv = helpers._resolve_delivery(delivery, title=title, message=message, name=name)
    except ValueError as e:
        return fail(str(e), trace_id=trace_id, error_code="INVALID_PARAM")

    try:
        from apscheduler.triggers.date import DateTrigger
        trigger = DateTrigger(run_date=target)
    except ImportError:
        return fail("APScheduler DateTrigger not available.",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    job_id = f"once_{int(_time.time() * 1000)}"

    try:
        scheduler.add_job(
            func=state._noop_fire,
            trigger=trigger,
            kwargs={"job_id": job_id},
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        return fail(f"Failed to add once job: {e}",
                    trace_id=trace_id, error_code="INTERNAL_ERROR")

    state._job_registry[job_id] = {
        "name": name or deliv.get("title", "one-shot job"),
        "kind": "once",
        "cron": "",
        "interval": "",
        "run_at": target.isoformat(),
        "delivery": deliv,
        "misfire_policy": "skip",  # once-jobs use fire_if_missed, not the policy trio
        "misfire_grace": misfire_grace or state.DEFAULT_MISFIRE_GRACE,
        "fire_if_missed": bool(fire_if_missed),
        "status": "scheduled",
        "last_fired_at": "",
        "created_at": n.isoformat(),
        "source": "manual",
    }
    state._save_jobs()

    return ok({
        "action_status": "scheduled",
        "action": "add_once",
        "job_id": job_id,
        "name": state._job_registry[job_id]["name"],
        "run_at": format_dt(target),
        "fire_if_missed": state._job_registry[job_id]["fire_if_missed"],
        "misfire_grace": state._job_registry[job_id]["misfire_grace"],
        "trace_id": trace_id,
    }, trace_id=trace_id)
