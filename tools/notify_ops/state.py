"""tools/notify_ops/state.py — Scheduler state + job registry + delivery log.

Extracted from the original tools/notify.py during the v1.0 @meta_tool
refactor. All shared mutable state lives here so it can be reset cleanly
between tests via reset_state(), and so action handlers don't need to know
about each other's storage details.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. _scheduler is a module-level singleton guarded by _scheduler_lock.
     Lazy-initialized by _get_scheduler() in helpers.py. NEVER access
     _scheduler directly from an action handler — always go through
     _get_scheduler() so the singleton is initialized on first use.

  2. _job_registry is the authoritative in-memory store of scheduled job
     metadata (title, message, run_at, status, cron for recurring jobs).
     APScheduler's own job store is NOT queryable for our metadata
     (DateTrigger/CronTrigger store only the firing schedule), so we keep
     a parallel dict. _save_jobs() persists it to disk so scheduled jobs
     survive process restarts; _load_jobs() reloads on startup.

  3. _delivery_log is a bounded in-memory log of recent sent notifications
     (max _MAX_DELIVERY_LOG = 50). It is NOT persisted — it exists for the
     `history` action so the LLM can verify "did my last notify() call
     actually deliver?". Bounded to prevent unbounded memory growth in
     long-running agents.

  4. reset_state() is called by tests (autouse fixture in conftest.py) to
     guarantee isolation. It shuts down the scheduler if running, clears
     the registry and delivery log, and resets the singleton to None so
     the next _get_scheduler() call re-initializes cleanly. NEVER call
     reset_state() in production code — it would silently nuke scheduled
     reminders.

  5. _save_jobs() / _load_jobs() use cfg.agent_root / ".notify_jobs" /
     "jobs.json" for persistence (v1.1: moved from workspace_root → agent_root
     to mirror the .understand/ + .schedule_jobs/ convention; job persistence
     is agent infrastructure, not user data). The directory is created lazily
     on first save. File writes are atomic (write to .tmp, then rename) to
     prevent partial-write corruption if the process dies mid-write.

PERSISTENCE + RESTART SEMANTICS:
  On process startup, the first _get_scheduler() call invokes _load_jobs()
  AFTER starting the scheduler. _load_jobs() re-registers every job from
  jobs.json back into APScheduler (DateTrigger / CronTrigger recalculated
  from the stored run_at / cron fields) AND repopulates _job_registry.
  Jobs whose run_at is already in the past are skipped (their fire time
  has passed — no point re-scheduling).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import cfg
from core.time_utils import now, parse_iso, _build_cron_trigger, get_timezone

# ── Scheduler singleton ───────────────────────────────────────────────────────

_scheduler: Any = None
_scheduler_lock = threading.Lock()

# ── Job metadata registry ─────────────────────────────────────────────────────
# Keyed by job_id (e.g. "reminder_1234567890" or "recurring_1234567890").
# Value shape:
#   {
#     "title":   str,
#     "message": str,
#     "run_at":  str (ISO 8601 — for DateTrigger jobs; "" for recurring),
#     "cron":    str (cron expr — for recurring jobs; "" for DateTrigger),
#     "status":  "scheduled" | "recurring",
#     "recurring": bool,
#   }
_job_registry: Dict[str, Dict[str, Any]] = {}

# ── Delivery log (bounded in-memory) ──────────────────────────────────────────
_delivery_log: List[Dict[str, Any]] = []
_MAX_DELIVERY_LOG = 50


def _jobs_path() -> Path:
    """Return the absolute path to the jobs.json persistence file.

    Centralized so tests can patch this function (or patch cfg.agent_root)
    to redirect persistence to a tmp_path. NEVER hardcode the path in callers.
    """
    return Path(cfg.agent_root) / ".notify_jobs" / "jobs.json"


def _save_jobs() -> None:
    """Persist _job_registry to agent_root/.notify_jobs/jobs.json.

    Atomic write: serialize to JSON, write to a .tmp sibling, then os.replace
    to the final path. This prevents partial-write corruption if the process
    dies mid-write (a real risk for long-running agents that get SIGKILL'd).

    Failures are swallowed and logged to stderr — persistence is best-effort.
    A failed save MUST NOT crash the calling action; the in-memory registry
    is still authoritative for the current session.
    """
    import sys
    try:
        path = _jobs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_job_registry, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception as e:
        # Best-effort: never crash on save failure.
        print(f"[notify_ops.state._save_jobs] WARNING: failed to persist jobs: {e}",
              file=sys.stderr)


def _load_jobs() -> None:
    """Load _job_registry from agent_root/.notify_jobs/jobs.json on startup.

    Called ONCE by _get_scheduler() after the scheduler is initialized. Reads
    the persisted registry and re-registers every job back into APScheduler:

      - DateTrigger jobs: re-create with DateTrigger(run_date=run_at). Skip
        if run_at is already in the past (fire time passed while offline).
      - CronTrigger (recurring) jobs: re-create via _build_cron_trigger(cron)
        (v1.1: DOW remap — standard cron 0=Sunday, not APScheduler's 0=Monday).

    Failures (missing file, corrupt JSON, APScheduler errors) are swallowed
    and logged — a corrupt persistence file MUST NOT prevent the scheduler
    from starting. The in-memory registry is rebuilt from whatever valid
    entries the loader could reconstruct.
    """
    import sys
    global _job_registry
    try:
        path = _jobs_path()
        if not path.exists():
            return  # First run — nothing to load.

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        if not isinstance(loaded, dict):
            return  # Corrupt — not a dict.

        # Re-register jobs in APScheduler + rebuild _job_registry.
        # Lazy import so state.py doesn't hard-depend on APScheduler being
        # installed — _load_jobs() is only called from _get_scheduler() which
        # already proved APScheduler is importable.
        from apscheduler.triggers.date import DateTrigger

        # Snapshot the scheduler we just initialized (caller passes None and
        # we use the module-level singleton). _get_scheduler() calls us right
        # after assigning _scheduler, so it's available here.
        sched = _scheduler
        if sched is None:
            return

        n = now()
        rebuilt: Dict[str, Dict[str, Any]] = {}

        for job_id, meta in loaded.items():
            if not isinstance(meta, dict):
                continue
            try:
                if meta.get("recurring"):
                    cron_expr = meta.get("cron", "")
                    if not cron_expr:
                        continue
                    # v1.1 DOW FIX: _build_cron_trigger remaps DOW 0=Sunday.
                    trigger = _build_cron_trigger(cron_expr, get_timezone())
                    sched.add_job(
                        func=_noop_fire,
                        trigger=trigger,
                        kwargs={
                            "title": meta.get("title", ""),
                            "message": meta.get("message", ""),
                        },
                        id=job_id,
                        replace_existing=True,
                    )
                    rebuilt[job_id] = meta
                else:
                    run_at_str = meta.get("run_at", "")
                    if not run_at_str:
                        continue
                    try:
                        run_at = parse_iso(run_at_str)
                    except (ValueError, TypeError):
                        continue
                    if run_at <= n:
                        # Fire time already passed while offline — skip.
                        continue
                    sched.add_job(
                        func=_noop_fire,
                        trigger=DateTrigger(run_date=run_at),
                        kwargs={
                            "title": meta.get("title", ""),
                            "message": meta.get("message", ""),
                        },
                        id=job_id,
                        replace_existing=True,
                    )
                    rebuilt[job_id] = meta
            except Exception as e:
                print(f"[notify_ops.state._load_jobs] WARNING: skipping job "
                      f"{job_id!r}: {e}", file=sys.stderr)
                continue

        _job_registry = rebuilt
    except Exception as e:
        print(f"[notify_ops.state._load_jobs] WARNING: failed to load jobs: {e}",
              file=sys.stderr)


def _noop_fire(title: str = "", message: str = "") -> None:
    """Job firing callback for re-loaded jobs.

    Re-loaded jobs use this stub instead of the real _send_notification
    because helpers.py would create a circular import (state → helpers →
    state) if state.py imported _send_notification at module load. The
    scheduler will still fire and call this; we delegate to the real
    _send_notification lazily at fire time so the import happens on the
    first firing, well after module initialization.
    """
    try:
        from tools.notify_ops.helpers import _send_notification
        _send_notification(title, message)
    except Exception:
        # Best-effort — never crash a scheduled job thread.
        pass


def _log_delivery(
    title: str,
    message: str,
    method: str,
    trace_id: str = "",
) -> None:
    """Append a delivery record to _delivery_log (bounded to 50 entries).

    The log exists for the `history` action — the LLM can verify "did my
    last notify(action='send') actually deliver?" by calling
    notify(action='history'). Bounded so long-running agents don't leak
    memory; older entries drop off the front.

    Each entry shape:
        {
            "title":    str,
            "message":  str,
            "method":   str ("plyer" | "notify-send" | "console"),
            "trace_id": str,
            "timestamp": str (ISO 8601 of when it was logged),
        }
    """
    entry: Dict[str, Any] = {
        "title": title,
        "message": message,
        "method": method,
        "trace_id": trace_id,
        "timestamp": now().isoformat(),
    }
    _delivery_log.append(entry)
    # Trim to bound — pop from front (oldest first).
    while len(_delivery_log) > _MAX_DELIVERY_LOG:
        _delivery_log.pop(0)


def reset_state() -> None:
    """Reset all module-level state. TEST-ONLY — never call in production.

    Called by the autouse `reset_state` fixture in conftest.py before each
    test to guarantee isolation. Order matters:
      1. Shut down scheduler (if running) — stops the background thread.
      2. Reset singleton to None — next _get_scheduler() will re-init.
      3. Clear _job_registry — no leakage of jobs from a previous test.
      4. Clear _delivery_log — no leakage of delivery history.
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass  # Scheduler may already be shut down — ignore.
            _scheduler = None
    _job_registry.clear()
    _delivery_log.clear()
