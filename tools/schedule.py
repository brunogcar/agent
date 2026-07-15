"""tools/schedule.py — Schedule meta-tool (v1.0).

Thin @tool facade. Routes all schedule actions to handlers in
schedule_ops/actions/ via the DISPATCH dict. Auto-discovered by registry.py
via the @tool decorator.

WHAT IT DOES:
  Schedules jobs (cron / interval / one-shot) that DELIVER via notify at fire
  time. notify stays focused on notification delivery; schedule owns the
  scheduling logic + offline recovery + calendar sync.

ACTIONS (9): add_cron | add_interval | add_once | list | cancel | modify |
             history | sync_calendar | test.

OFFLINE RECOVERY:
  If the server is offline when a job is due, APScheduler never queues it.
  On next boot, catch_up_missed_jobs() (server.py startup daemon) computes
  missed fires per job, applies a grace window + misfire policy (skip /
  fire_last / fire_all), and delivers via notify. last_fired_at is the
  durable signal that survives crashes.

DELIVERY BACKEND (v1.0):
  Only notify is supported as a delivery backend:
      schedule(action="add_cron", cron="0 9 * * *",
               delivery={"tool":"notify","action":"send",
                         "title":"Standup","message":"..."})
  Or shorthand (schedule builds the delivery from title+message):
      schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="...")
  Future backends (v2.0+): ntfy.sh, Slack, Discord, Telegram, email.

NOT PARALLEL_SAFE — schedule owns a BackgroundScheduler singleton + shared
_job_registry; concurrent calls could race on job creation. NOT in
PARALLEL_SAFE; IS in _TOOL_MAP (so parallel can still dispatch to it, just
not concurrently with itself).
"""
from __future__ import annotations

import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import schedule_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import schedule_ops  # noqa: F401
from tools.schedule_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("schedule", {}),
    doc_sections=[
        "SCHEDULE TOOL — Cron / interval / one-shot jobs delivered via notify:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Cron recurring job | schedule(add_cron) | 5-field cron (0=Sunday), e.g. '0 9 * * *' = 9am daily |",
        " | Interval recurring | schedule(add_interval) | duration e.g. '10m'/'2h'/'1d' |",
        " | One-shot at a time | schedule(add_once) | run_at = ISO | 'in 30m' | '9am' | '2026-07-16 09:00' |",
        " | List jobs | schedule(list) | All cron/interval/once jobs + metadata |",
        " | Cancel a job | schedule(cancel) | By job_id |",
        " | Modify a job | schedule(modify) | Update cron/interval/run_at/delivery/misfire policy |",
        " | Recent deliveries | schedule(history) | In-memory log of fired jobs |",
        " | Sync iCal calendar | schedule(sync_calendar) | Fetch .ics URL → add_once jobs per event |",
        " | Test delivery | schedule(test) | Fire a test via notify (no job created) |",
        "",
        "OFFLINE RECOVERY: jobs missed while the server was offline are caught up",
        "at boot via misfire_policy (skip | fire_last [default] | fire_all) within",
        "a misfire_grace window (default 24h). last_fired_at is persisted durably.",
        "",
        "DELIVERY: notify as backend. Pass delivery={...} for full control, or",
        "title+message for shorthand. v1.0 = notify only; ntfy/Slack/Discord/etc = v2.0+.",
        "",
        "PARAMETERS:",
        " - action (required) — one of the 9 actions above.",
        " - cron (add_cron) — 5-field cron, 0=Sunday (e.g. '0 9 * * 1' = Mon 9am).",
        " - interval (add_interval) — duration: '10m'/'2h'/'1d'/'1h30m'.",
        " - run_at (add_once) — ISO | 'in 30m' | '9am' | '2026-07-16T09:00:00'.",
        " - message (required for add_*) — delivery body (or use delivery dict).",
        " - title (optional) — delivery title (default job name).",
        " - name (optional) — human label for the job.",
        " - delivery (optional dict) — full delivery spec {tool,action,title,message,...}.",
        " - job_id (cancel/modify) — identifier from the add_* response.",
        " - misfire_policy (optional) — skip | fire_last | fire_all (default fire_last).",
        " - misfire_grace (optional) — duration, default '24h'.",
        " - fire_if_missed (add_once, optional bool) — fire on next boot if run_at passed while offline.",
        " - calendar_url (sync_calendar) — http(s) .ics URL.",
        " - trace_id (optional) — forwarded to all responses for observability.",
        "",
        "STATUS SCHEMA:",
        " - response.status is 'success' or 'error' (standardized via core.contracts.ok/fail).",
        " - response.data.action_status preserves semantic status ('scheduled'/'cancelled'/'modified'/'ok'/'synced').",
        " - response.duration_ms is set by this facade.",
    ],
)
def schedule(
    action: str = "",
    name: str = "",
    cron: str = "",
    interval: str = "",
    run_at: str = "",
    delivery: dict = None,
    title: str = "",
    message: str = "",
    job_id: str = "",
    misfire_policy: str = "",
    misfire_grace: str = "",
    fire_if_missed: bool = False,
    calendar_url: str = "",
    limit: int = 20,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """schedule meta-tool — add_cron | add_interval | add_once | list | cancel | modify | history | sync_calendar | test."""
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "schedule", f"action={action}")

    if not action:
        return {
            "status": "error", "data": None,
            "error": "action is required (add_cron | add_interval | add_once | list | cancel | modify | history | sync_calendar | test)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("schedule", {})
    op_info = dispatch.get(action)
    if op_info is None:
        valid = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error", "data": None,
            "error": f"Unknown action '{action}'. Use: {valid}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]
    handler_kwargs = {
        "action": action, "name": name, "cron": cron, "interval": interval,
        "run_at": run_at, "delivery": delivery, "title": title, "message": message,
        "job_id": job_id, "misfire_policy": misfire_policy,
        "misfire_grace": misfire_grace, "fire_if_missed": fire_if_missed,
        "calendar_url": calendar_url, "limit": limit, "trace_id": trace_id,
    }
    # Forward any extra kwargs so action-specific params (e.g. history's limit
    # when passed positionally by direct callers) reach the handler.
    handler_kwargs.update(kwargs)

    start = time.time()
    try:
        result = handler(**handler_kwargs)
    except Exception as e:
        return {
            "status": "error", "data": None,
            "error": f"Schedule action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error", "data": None,
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    if result.get("status") == "error":
        tracer.step(trace_id, "schedule", f"action={action}:failed")
    else:
        tracer.step(trace_id, "schedule", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
