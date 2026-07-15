"""tools/schedule_ops/actions/modify.py — Modify a job's schedule/metadata.

Updates the persisted registry + re-creates the APScheduler job with the new
trigger (replace_existing=True). Only the supplied fields change; omitted
fields keep their current values.
"""
from __future__ import annotations

from core.contracts import ok, fail
from core.time_utils import parse_human, parse_iso, now, format_dt, parse_duration, cron_next_fire, get_timezone, _build_cron_trigger
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


@register_action(
    "schedule", "modify",
    help_text="""modify — Modify a job's schedule and/or delivery metadata.
Required: job_id
Optional (any subset): name, cron, interval, run_at, delivery, title, message,
          misfire_policy, misfire_grace, fire_if_missed, trace_id
Returns: {action_status: "modified", job_id, changed: [...], trace_id?}

NOTE: changing cron/interval/run_at re-creates the APScheduler trigger.
Changing delivery/title/message updates the persisted delivery spec only
(the next fire uses the new spec).""",
    examples=[
        'schedule(action="modify", job_id="cron_123", cron="0 10 * * *")',
        'schedule(action="modify", job_id="once_456", message="Updated text")',
    ],
)
def _action_modify(
    job_id: str = "",
    name: str = "",
    cron: str = "",
    interval: str = "",
    run_at: str = "",
    delivery: dict = None,
    title: str = "",
    message: str = "",
    misfire_policy: str = "",
    misfire_grace: str = "",
    fire_if_missed: bool = None,  # None = unchanged
    trace_id: str = "",
    **kwargs,
) -> dict:
    if not job_id or not job_id.strip():
        return fail("job_id is required for modify",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    job_id = job_id.strip()
    meta = state._job_registry.get(job_id)
    if meta is None:
        return fail(f"No job with job_id {job_id!r}",
                    trace_id=trace_id, error_code="NOT_FOUND")
    if meta.get("status") == "cancelled":
        return fail(f"job {job_id!r} is cancelled — modify not allowed",
                    trace_id=trace_id, error_code="INVALID_STATE")

    changed = []

    # Validate new schedule fields BEFORE mutating, so a bad value leaves the
    # job intact (atomic update semantics).
    new_cron = cron.strip() if cron else ""
    new_interval = interval.strip() if interval else ""
    new_run_at_target = None
    if new_cron and meta.get("kind") != "cron":
        return fail(f"job {job_id!r} is kind={meta.get('kind')!r}, cannot set cron",
                    trace_id=trace_id, error_code="INVALID_PARAM")
    if new_interval and meta.get("kind") != "interval":
        return fail(f"job {job_id!r} is kind={meta.get('kind')!r}, cannot set interval",
                    trace_id=trace_id, error_code="INVALID_PARAM")
    if run_at and meta.get("kind") != "once":
        return fail(f"job {job_id!r} is kind={meta.get('kind')!r}, cannot set run_at",
                    trace_id=trace_id, error_code="INVALID_PARAM")
    if new_cron:
        try:
            _build_cron_trigger(new_cron, get_timezone())
        except Exception as e:
            return fail(f"Invalid cron {new_cron!r}: {e}",
                        trace_id=trace_id, error_code="INVALID_PARAM")
    if new_interval:
        try:
            parse_duration(new_interval)
        except ValueError as e:
            return fail(f"Invalid interval {new_interval!r}: {e}",
                        trace_id=trace_id, error_code="INVALID_PARAM")
    if run_at:
        try:
            new_run_at_target = parse_human(run_at)
            if new_run_at_target <= now():
                return fail("run_at must be in the future",
                            trace_id=trace_id, error_code="INVALID_PARAM")
        except ValueError as e:
            return fail(f"Invalid run_at {run_at!r}: {e}",
                        trace_id=trace_id, error_code="INVALID_PARAM")
    if misfire_policy and misfire_policy not in state.VALID_MISFIRE_POLICIES:
        return fail(f"misfire_policy must be one of {sorted(state.VALID_MISFIRE_POLICIES)}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    # Apply metadata changes.
    if name:
        meta["name"] = name; changed.append("name")
    if new_cron:
        meta["cron"] = new_cron; changed.append("cron")
    if new_interval:
        meta["interval"] = new_interval; changed.append("interval")
    if new_run_at_target is not None:
        meta["run_at"] = new_run_at_target.isoformat(); changed.append("run_at")
    if misfire_policy:
        meta["misfire_policy"] = misfire_policy; changed.append("misfire_policy")
    if misfire_grace:
        meta["misfire_grace"] = misfire_grace; changed.append("misfire_grace")
    if fire_if_missed is not None:
        meta["fire_if_missed"] = bool(fire_if_missed); changed.append("fire_if_missed")
    # Delivery: rebuild if any delivery/title/message supplied.
    if delivery or title or message:
        base_deliv = dict(meta.get("delivery", {}))
        if delivery and isinstance(delivery, dict):
            base_deliv.update(delivery)
        if title:
            base_deliv["title"] = title
        if message:
            base_deliv["message"] = message
        try:
            resolved = helpers._resolve_delivery(base_deliv, title=title, message=message, name=meta.get("name", ""))
        except ValueError as e:
            return fail(str(e), trace_id=trace_id, error_code="INVALID_PARAM")
        meta["delivery"] = resolved; changed.append("delivery")

    # Re-create the APScheduler trigger if schedule fields changed.
    if new_cron or new_interval or new_run_at_target is not None:
        scheduler = helpers._get_scheduler()
        if scheduler is not None:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
            try:
                if meta["kind"] == "cron":
                    trigger = _build_cron_trigger(meta["cron"], get_timezone())
                elif meta["kind"] == "interval":
                    from apscheduler.triggers.interval import IntervalTrigger
                    trigger = IntervalTrigger(seconds=parse_duration(meta["interval"]).total_seconds())
                else:
                    from apscheduler.triggers.date import DateTrigger
                    trigger = DateTrigger(run_date=parse_iso(meta["run_at"]))
                scheduler.add_job(
                    func=state._noop_fire, trigger=trigger,
                    kwargs={"job_id": job_id}, id=job_id, replace_existing=True,
                )
            except Exception as e:
                return fail(f"Failed to re-create trigger: {e}",
                            trace_id=trace_id, error_code="INTERNAL_ERROR")

    state._save_jobs()

    return ok({
        "action_status": "modified", "action": "modify", "job_id": job_id,
        "changed": changed, "trace_id": trace_id,
    }, trace_id=trace_id)
