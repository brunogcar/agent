"""tools/schedule_ops/actions/list.py — List all scheduled jobs.

The action_name is "list" and the module is list.py (matches report_ops'
convention; list_workflows.py is the legacy outlier being phased out).
"""
from __future__ import annotations

from core.contracts import ok
from core.time_utils import now, format_dt, parse_iso, cron_next_fire, parse_duration
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


def _compute_next_run(meta: dict):
    """Best-effort next-run computation for display (may be '' for fired/past)."""
    kind = meta.get("kind", "")
    st = meta.get("status", "")
    if st in ("cancelled", "fired"):
        return ""
    try:
        if kind == "cron" and meta.get("cron"):
            nxt = cron_next_fire(meta["cron"])
            return format_dt(nxt) if nxt else ""
        if kind == "interval" and meta.get("interval"):
            last = meta.get("last_fired_at") or meta.get("created_at", "")
            base = parse_iso(last) if last else now()
            return format_dt(base + parse_duration(meta["interval"]))
        if kind == "once" and meta.get("run_at"):
            return format_dt(parse_iso(meta["run_at"]))
    except Exception:
        return ""
    return ""


@register_action(
    "schedule", "list",
    help_text="""list — List all scheduled jobs (cron / interval / once).
Optional: trace_id
Returns: {action_status: "ok", jobs: [...], count, note?}""",
    examples=['schedule(action="list")'],
)
def _action_list(trace_id: str = "", **kwargs) -> dict:
    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return ok({
            "action_status": "ok", "action": "list", "jobs": [], "count": 0,
            "note": "Scheduler not running (APScheduler not installed).",
            "trace_id": trace_id,
        }, trace_id=trace_id)

    jobs = []
    for job_id, meta in state._job_registry.items():
        jobs.append({
            "job_id": job_id,
            "name": meta.get("name", ""),
            "kind": meta.get("kind", ""),
            "cron": meta.get("cron", ""),
            "interval": meta.get("interval", ""),
            "run_at": meta.get("run_at", ""),
            "status": meta.get("status", ""),
            "next_run": _compute_next_run(meta),
            "last_fired_at": meta.get("last_fired_at", ""),
            "misfire_policy": meta.get("misfire_policy", ""),
            "misfire_grace": meta.get("misfire_grace", ""),
            "fire_if_missed": meta.get("fire_if_missed", False),
            "source": meta.get("source", "manual"),
            "delivery_title": meta.get("delivery", {}).get("title", ""),
            "delivery_message": meta.get("delivery", {}).get("message", ""),
        })
    return ok({
        "action_status": "ok", "action": "list", "jobs": jobs, "count": len(jobs),
        "trace_id": trace_id,
    }, trace_id=trace_id)
