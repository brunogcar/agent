"""tools/notify.py — Notify meta-tool (v1.0).

Thin @tool facade. Routes all notify actions to handlers in
notify_ops/actions/ via the DISPATCH dict. Auto-discovered by
registry.py via the @tool decorator.

v1.0 changes (the @meta_tool refactor):
  - Now a meta-tool with 8 actions: send | schedule | cancel | list |
    recurring | modify | history | test.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - New params: cron (recurring action), trace_id (observability).
  - All implementation logic moved to notify_ops/ subpackage.
  - Action handlers use ok()/fail() from core.contracts for standardized
    response shape. Semantic statuses ("sent", "scheduled", "cancelled",
    "ok") preserved in data.action_status — response.status is now
    "success"/"error" per the standardized contract.

PARALLEL_SAFE — notify IS in core/parallel_executor.py's PARALLEL_SAFE
frozenset. Notifications are stateless; concurrent calls don't interfere
(APScheduled jobs are guarded by _scheduler_lock).

KNOWN ISSUE (not fixed here — out of scope for this refactor):
  tools/parallel.py's _TOOL_MAP does not include "notify". This means
  the parallel executor's TOOL_MAP-based dispatch path skips notify even
  though PARALLEL_SAFE lists it. The router still routes to notify via
  the standard tool dispatch path, so end-to-end behavior is correct in
  the common case — but parallel() with notify in the tool list will not
  use the parallel executor's notify-specific path. Document this in the
  parallel staging dir's worklog when that refactor lands.

FUTURE INTEGRATION — schedule tool:
  A future `schedule` tool will own calendar sync, iCal/CalDAV, and richer
  cron semantics. That schedule tool will USE notify as its delivery
  mechanism — notify stays focused on notification delivery, not
  scheduling logic beyond simple delays. See
  notify_ops/actions/recurring.py for the future delivery-backend roadmap
  (ntfy.sh / Slack / Discord / Telegram / email).
"""
from __future__ import annotations

import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import notify_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import notify_ops  # noqa: F401
from tools.notify_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("notify", {}),
    doc_sections=[
        "NOTIFY TOOL — Desktop notifications + scheduled reminders:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Immediate notification | notify(send) | Desktop alert (plyer/notify-send/console) |",
        " | Schedule a reminder | notify(schedule) | APScheduler DateTrigger after N minutes |",
        " | Cancel a reminder | notify(cancel) | Remove job by job_id |",
        " | List scheduled jobs | notify(list) | Show all pending notifications |",
        " | Recurring notification | notify(recurring) | Cron-style via APScheduler CronTrigger |",
        " | Modify a job | notify(modify) | Update title/message without cancel+re-create |",
        " | Recently sent | notify(history) | In-memory log of delivered notifications |",
        " | Test delivery | notify(test) | Verify notification pipeline works |",
        "",
        "Platform: Windows (plyer), Linux (notify-send), fallback (console).",
        "PARALLEL_SAFE — notifications are stateless.",
        "",
        "PARAMETERS:",
        " - action (required) — one of the actions listed above.",
        " - title (optional) — notification title (default 'Agent' or 'Agent Reminder').",
        " - message (required for send/schedule/recurring) — notification body.",
        " - timeout (optional, seconds, default 5) — how long the toast shows.",
        " - delay_minutes (required for schedule, >0) — minutes from now to fire.",
        " - job_id (required for cancel/modify) — identifier from schedule/recurring response.",
        " - cron (required for recurring) — 5-field cron expression (e.g. '0 9 * * *' = 9am daily).",
        " - trace_id (optional) — forwarded to all responses for observability threading.",
        "",
        "STATUS SCHEMA:",
        " - response.status is 'success' or 'error' (standardized via core.contracts.ok/fail).",
        " - response.data.action_status preserves semantic status ('sent', 'scheduled', 'cancelled', 'ok', 'modified').",
        " - response.duration_ms is set by this facade (rounded milliseconds).",
    ],
)
def notify(
    action: str = "",
    title: str = "",
    message: str = "",
    timeout: int = 5,
    delay_minutes: int = 0,
    job_id: str = "",
    cron: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """notify meta-tool — send | schedule | cancel | list | recurring | modify | history | test."""
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "notify", f"action={action}")

    if not action:
        return {
            "status": "error",
            "data": None,
            "error": "action is required (send | schedule | cancel | list | recurring | modify | history | test)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("notify", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error",
            "data": None,
            "error": f"Unknown action '{action}'. Use: {valid_actions}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]

    # Forward all facade params to the handler. Handlers are tolerant of
    # extra kwargs (**kwargs) so unused params are silently ignored — this
    # lets us evolve the facade signature without breaking existing
    # handlers, and lets handlers pick only the params they need.
    handler_kwargs = {
        "action": action,
        "title": title,
        "message": message,
        "timeout": timeout,
        "delay_minutes": delay_minutes,
        "job_id": job_id,
        "cron": cron,
        "trace_id": trace_id,
    }

    start = time.time()
    try:
        result = handler(**handler_kwargs)
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "error": f"Notify action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error",
            "data": None,
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    # Trace success/failure for observability. Only the action_status field
    # (in data) carries the semantic status; the top-level status is now
    # 'success'/'error' per the standardized contract.
    if result.get("status") == "error":
        tracer.step(trace_id, "notify", f"action={action}:failed")
    else:
        tracer.step(trace_id, "notify", f"action={action}:complete")

    # The facade adds duration_ms — handlers don't track this themselves
    # (matches the consult/python facade pattern). This keeps timing
    # instrumentation in ONE place: the facade.
    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
