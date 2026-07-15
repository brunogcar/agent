"""tools/schedule_ops/helpers.py — Shared utilities for schedule actions.

Two responsibilities:
  1. _get_scheduler() — lazy APScheduler singleton + persistence reload.
  2. _fire_job() — deliver a scheduled job via its delivery backend (notify
     in v1.0; ntfy.sh / Slack / Discord / Telegram / email planned for v2.0).
  3. _resolve_delivery() — normalize the delivery spec from action params.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. _get_scheduler() is the ONLY entry point to the _scheduler singleton.
     Returns None on ImportError (APScheduler not installed) so callers can
     produce a graceful error. On first init: start scheduler + _load_jobs()
     + _reload_jobs_into_scheduler(). catch_up_missed_jobs() runs separately
     (server.py startup daemon) to avoid blocking the first schedule() call.

  2. _fire_job() is the APScheduler callback (via state._noop_fire) AND the
     catch-up delivery path. It calls notify(action="send", ...) by default.
     Loose coupling: `from tools.notify import notify` works whether notify
     is legacy (raw-dict return) or v1.0 (ok/fail envelope) — we only inspect
     result.get("status") defensively. NEVER hard-import notify_ops (it may
     not be present in this commit).

  3. _fire_job marks_fired ONLY for live fires (catch_up=False). Catch-up
     deliveries are marked by catch_up_missed_jobs() after the loop, so
     last_fired_at lands on the most recent missed fire (accurate + avoids
     double-writes).

  4. _resolve_delivery() validates that the delivery tool is "notify" (v1.0
     only). Other backends raise ValueError → actions translate to fail().
"""
from __future__ import annotations

import sys
from typing import Any, Optional, Tuple

from core.time_utils import now, format_dt


def _get_scheduler() -> Optional[object]:
    """Return the singleton BackgroundScheduler, initializing on first call.

    Returns None if APScheduler is not installed. On first successful init:
      1. Create BackgroundScheduler(daemon=True).
      2. Start it (background thread).
      3. state._load_jobs() — read persisted _job_registry from disk.
      4. state._reload_jobs_into_scheduler(sched) — re-add future fires.

    catch_up_missed_jobs() is NOT called here — it runs in a server.py startup
    daemon so the first schedule() call isn't blocked by catch-up deliveries.
    Thread-safe via state._scheduler_lock.
    """
    from tools.schedule_ops import state

    with state._scheduler_lock:
        if state._scheduler is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                sched = BackgroundScheduler(daemon=True)
                sched.start()
                state._scheduler = sched
                state._load_jobs()
                state._reload_jobs_into_scheduler(sched)
            except ImportError:
                return None
        return state._scheduler


def _resolve_delivery(
    delivery: Optional[dict],
    title: str = "",
    message: str = "",
    name: str = "",
) -> dict:
    """Normalize a delivery spec into a fully-formed call dict.

    If `delivery` is provided (dict), use it; fill missing title/message from
    the explicit args. If not, build a default notify(send) spec from
    title/message/name.

    The returned dict always has:
      "tool":    "notify"  (v1.0 — only notify supported)
      "action":  "send"    (default)
      "title":   str
      "message": str

    Raises ValueError if the delivery tool is not "notify" (v1.0 limitation).
    """
    if delivery and isinstance(delivery, dict):
        d = dict(delivery)
    else:
        d = {}
    tool = (d.get("tool") or "notify").strip().lower()
    if tool != "notify":
        raise ValueError(
            f"unsupported delivery tool {tool!r} — schedule v1.0 only supports "
            f"'notify' (ntfy.sh/Slack/Discord/Telegram/email are planned for v2.0)"
        )
    d["tool"] = "notify"
    d.setdefault("action", "send")
    # Fill title/message from explicit args if the spec omitted them.
    if not d.get("title"):
        d["title"] = title or name or "Scheduled"
    if not d.get("message"):
        d["message"] = message
    return d


def _call_notify(delivery: dict) -> dict:
    """Invoke notify(**delivery) and return its response dict.

    Loose coupling: works whether notify is legacy (raw-dict return) or v1.0
    (ok/fail envelope). Never raises — delivery failures are surfaced as a
    dict with status="error" so callers/_log_delivery can record them.
    """
    # Strip "tool" — notify() doesn't accept it.
    kwargs = {k: v for k, v in delivery.items() if k != "tool"}
    try:
        from tools.notify import notify
        result = notify(**kwargs)
        if not isinstance(result, dict):
            return {"status": "error", "error": f"notify returned {type(result).__name__}"}
        return result
    except Exception as e:
        return {"status": "error", "error": f"notify delivery failed: {e}"}


def _fire_job(
    job_id: str = "",
    fire_time: Any = None,
    catch_up: bool = False,
    trace_id: str = "",
) -> dict:
    """Deliver a scheduled job via its delivery backend.

    Called by:
      - APScheduler (via state._noop_fire) for LIVE fires — fire_time=now(),
        catch_up=False, marks_fired after delivery.
      - catch_up_missed_jobs() for OFFLINE-recovered fires — fire_time=missed
        instant, catch_up=True, message stamped; marking handled by caller.

    Returns the delivery result dict (for logging/inspection). Never raises —
    a crashing job thread must not take down the scheduler.
    """
    from tools.schedule_ops import state

    ft = fire_time or now()
    meta = state._job_registry.get(job_id)
    if meta is None:
        # Job vanished (cancelled / expired). Not an error — just no-op.
        return {"status": "noop", "error": f"job {job_id!r} not in registry"}

    delivery = dict(meta.get("delivery", {}))
    # Stamp catch-up fires so the recipient can distinguish them from live.
    if catch_up:
        base_msg = delivery.get("message", "")
        delivery["message"] = (
            f"{base_msg} [catch-up for fire @ {format_dt(ft)}]"
        ).strip()

    result = _call_notify(delivery)

    # Record in the in-memory delivery log (for the history action).
    try:
        state._log_delivery(job_id, ft, delivery, result, catch_up, trace_id)
    except Exception:
        pass

    # Trace for observability.
    try:
        from core.tracer import tracer
        tracer.step(
            trace_id or "schedule_fire",
            "schedule_fire",
            f"job={job_id!r} catch_up={catch_up} status={result.get('status')}",
        )
    except Exception:
        pass

    # Live fires mark themselves fired; catch-up fires are marked by the
    # caller (catch_up_missed_jobs) so last_fired_at lands on the most recent
    # missed instant, not the catch-up delivery time.
    if not catch_up:
        try:
            state.mark_fired(job_id, ft)
        except Exception as e:
            print(f"[schedule_ops.helpers._fire_job] WARNING: mark_fired failed "
                  f"for {job_id!r}: {e}", file=sys.stderr)

    return result
