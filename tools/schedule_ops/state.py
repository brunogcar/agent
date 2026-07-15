"""tools/schedule_ops/state.py — Scheduler state + job registry + catch-up logic.

Extracted as the persistence + recovery layer for the schedule tool. All
shared mutable state lives here so it can be reset cleanly between tests via
reset_state(), and so action handlers don't need to know about each other's
storage details.

[DESIGN] KEY INVARIANTS — read before modifying:

  1. _scheduler is a module-level singleton guarded by _scheduler_lock.
     Lazy-initialized by _get_scheduler() in helpers.py. NEVER access
     _scheduler directly from an action handler — always go through
     _get_scheduler().

  2. _job_registry is the authoritative in-memory store of scheduled job
     metadata. APScheduler's own job store is NOT queryable for our metadata
     (triggers store only the firing schedule), so we keep a parallel dict.
     _save_jobs() persists it to disk so jobs survive process restarts;
     _load_jobs() reloads on startup.

  3. PERSISTENCE PATH: cfg.agent_root / ".schedule_jobs" / "jobs.json" — at
     the AGENT ROOT (not workspace), mirroring the .understand/ convention.
     Job persistence is agent infrastructure, not user workspace data.
     Atomic write (tmp + os.replace) prevents partial-write corruption.

  4. OFFLINE RECOVERY (the key feature): if the server is offline when a job
     is due, APScheduler never queues it — the fire is silently lost. We
     recover via catch_up_missed_jobs():
       - For each job, compute the fire times in (last_fired_at, now].
       - Drop any older than the job's misfire_grace window (default 24h).
       - Apply the job's misfire_policy:
           skip       — discard all missed fires.
           fire_last  — deliver ONCE for the most recent missed fire. (default)
           fire_all   — deliver each missed fire in order (capped at 50).
       - Update last_fired_at so the same window is never re-processed.
     This runs in a daemon thread at server startup (server.py) so it doesn't
     block boot, and is also callable directly for tests.

  5. mark_fired(job_id, fire_time) is called after EVERY successful delivery
     (both live and catch-up). It updates last_fired_at + persists. This is
     the durable signal that survives crashes — if the process dies between
     delivery and mark_fired, the next boot may re-deliver once (rare
     double-fire, accepted tradeoff for v1.0 simplicity).

  6. reset_state() is TEST-ONLY — never call in production. It shuts down
     the scheduler, clears the registry + delivery log + catch-up guard.

JOB REGISTRY ENTRY SHAPE:
  {
    "name":            str,   # human label
    "kind":            "cron" | "interval" | "once",
    "cron":            str,   # 5-field cron (kind=="cron")
    "interval":        str,   # duration string e.g. "10m" (kind=="interval")
    "run_at":          str,   # ISO 8601 (kind=="once")
    "delivery":        dict,  # {"tool":"notify","action":"send","title":..,"message":..}
    "misfire_policy":  str,   # "skip" | "fire_last" | "fire_all"
    "misfire_grace":   str,   # duration string, default "24h"
    "fire_if_missed":  bool,  # once-jobs only
    "status":          "scheduled" | "recurring" | "fired" | "cancelled",
    "last_fired_at":   str,   # ISO, "" if never fired
    "created_at":      str,   # ISO
    "source":          str,   # "manual" | "calendar:<url>"
  }
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import cfg
from core.time_utils import now, parse_iso, parse_duration, compute_missed_fires, format_dt

# ── Scheduler singleton ───────────────────────────────────────────────────────

_scheduler: Any = None
_scheduler_lock = threading.Lock()

# ── Job metadata registry ─────────────────────────────────────────────────────
_job_registry: Dict[str, Dict[str, Any]] = {}

# ── Delivery log (bounded in-memory) ──────────────────────────────────────────
_delivery_log: List[Dict[str, Any]] = []
_MAX_DELIVERY_LOG = 100

# ── Catch-up guard (run once per process) ─────────────────────────────────────
_catch_up_done = False
_catch_up_lock = threading.Lock()

# Default misfire policy / grace / fire_all cap.
DEFAULT_MISFIRE_POLICY = "fire_last"
DEFAULT_MISFIRE_GRACE = "24h"
MAX_FIRE_ALL = 50

VALID_MISFIRE_POLICIES = frozenset({"skip", "fire_last", "fire_all"})
VALID_KINDS = frozenset({"cron", "interval", "once"})


def _jobs_path() -> Path:
    """Return the absolute path to the jobs.json persistence file.

    Lives at cfg.agent_root / ".schedule_jobs" / "jobs.json" — at the AGENT
    ROOT (mirrors .understand/), NOT under workspace/. Centralized so tests
    can patch cfg.agent_root to redirect persistence to a tmp_path.
    """
    return Path(cfg.agent_root) / ".schedule_jobs" / "jobs.json"


def _save_jobs() -> None:
    """Persist _job_registry to agent_root/.schedule_jobs/jobs.json (atomic).

    Atomic write: serialize to JSON, write to a .tmp sibling, then os.replace.
    Failures are swallowed + logged to stderr — persistence is best-effort; a
    failed save MUST NOT crash the calling action.
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
        print(f"[schedule_ops.state._save_jobs] WARNING: failed to persist jobs: {e}",
              file=sys.stderr)


def _load_jobs() -> None:
    """Load _job_registry from jobs.json on startup (metadata only).

    Called ONCE by _get_scheduler() after the scheduler is initialized. Reads
    the persisted registry into _job_registry. Does NOT re-add jobs to
    APScheduler — that's _reload_jobs_into_scheduler()'s job (separated so
    catch_up_missed_jobs can reason about past fires without APScheduler
    interference). Failures are swallowed + logged.
    """
    import sys
    global _job_registry
    try:
        path = _jobs_path()
        if not path.exists():
            return  # First run.
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return  # Corrupt.
        # Defensive: keep only dict-valued entries.
        _job_registry = {k: v for k, v in loaded.items() if isinstance(v, dict)}
    except Exception as e:
        print(f"[schedule_ops.state._load_jobs] WARNING: failed to load jobs: {e}",
              file=sys.stderr)


def _reload_jobs_into_scheduler(sched: Any) -> None:
    """Re-add persisted jobs to APScheduler for FUTURE fires.

    Called by _get_scheduler() after _load_jobs(). For each job:
      - cron / interval: always re-add (recurring — they have future fires).
      - once: re-add ONLY if run_at is in the future. Past once-jobs are
        handled by catch_up_missed_jobs() (fired once if fire_if_missed).
    Uses _noop_fire as the APScheduler callback (delegates to the real
    _fire_job lazily at fire time to avoid a state→helpers circular import).
    """
    import sys
    from core.time_utils import cron_next_fire
    n = now()
    for job_id, meta in list(_job_registry.items()):
        if meta.get("status") == "cancelled":
            continue
        kind = meta.get("kind", "")
        try:
            if kind == "cron":
                from core.time_utils import _build_cron_trigger
                from core.time_utils import get_timezone
                trigger = _build_cron_trigger(meta["cron"], get_timezone())
                sched.add_job(
                    func=_noop_fire,
                    trigger=trigger,
                    kwargs={"job_id": job_id},
                    id=job_id,
                    replace_existing=True,
                )
            elif kind == "interval":
                from apscheduler.triggers.interval import IntervalTrigger
                secs = parse_duration(meta["interval"]).total_seconds()
                sched.add_job(
                    func=_noop_fire,
                    trigger=IntervalTrigger(seconds=secs),
                    kwargs={"job_id": job_id},
                    id=job_id,
                    replace_existing=True,
                )
            elif kind == "once":
                run_at = parse_iso(meta["run_at"])
                if run_at <= n:
                    continue  # Past — catch_up handles it; don't re-add.
                from apscheduler.triggers.date import DateTrigger
                sched.add_job(
                    func=_noop_fire,
                    trigger=DateTrigger(run_date=run_at),
                    kwargs={"job_id": job_id},
                    id=job_id,
                    replace_existing=True,
                )
        except Exception as e:
            print(f"[schedule_ops.state._reload_jobs_into_scheduler] WARNING: "
                  f"skipping job {job_id!r}: {e}", file=sys.stderr)


def _noop_fire(job_id: str = "") -> None:
    """APScheduler callback for re-loaded jobs.

    Delegates to the real helpers._fire_job lazily at fire time (avoids the
    state→helpers circular import at module load). Never raises — a crashing
    scheduled job thread must not take down the scheduler.
    """
    try:
        from tools.schedule_ops.helpers import _fire_job
        _fire_job(job_id=job_id)
    except Exception:
        pass


def mark_fired(job_id: str, fire_time: Any = None) -> None:
    """Record that a job fired successfully. Updates last_fired_at + persists.

    Called after EVERY successful delivery (live + catch-up). This is the
    durable signal that survives crashes — catch_up_missed_jobs uses
    last_fired_at as the exclusive lower bound for missed-fire computation.
    """
    ft = fire_time or now()
    meta = _job_registry.get(job_id)
    if meta is None:
        return
    meta["last_fired_at"] = (ft.isoformat() if hasattr(ft, "isoformat") else str(ft))
    # once-jobs that have fired are done.
    if meta.get("kind") == "once" and meta.get("status") != "cancelled":
        meta["status"] = "fired"
    _save_jobs()


def _log_delivery(
    job_id: str,
    fire_time: Any,
    delivery: dict,
    result: Any,
    catch_up: bool,
    trace_id: str = "",
) -> None:
    """Append a delivery record to _delivery_log (bounded to 100 entries)."""
    entry: Dict[str, Any] = {
        "job_id": job_id,
        "fire_time": fire_time.isoformat() if hasattr(fire_time, "isoformat") else str(fire_time),
        "title": delivery.get("title", ""),
        "message": delivery.get("message", ""),
        "catch_up": catch_up,
        "result_status": (result.get("status") if isinstance(result, dict) else str(result)),
        "trace_id": trace_id,
        "timestamp": now().isoformat(),
    }
    _delivery_log.append(entry)
    while len(_delivery_log) > _MAX_DELIVERY_LOG:
        _delivery_log.pop(0)


# ── Offline recovery: catch-up of missed fires ──────────────────────────────

def _within_grace(fire_time: Any, grace_str: str, reference: Any = None) -> bool:
    """True if fire_time is within grace_str of reference (default now)."""
    try:
        grace = parse_duration(grace_str)
    except ValueError:
        grace = parse_duration(DEFAULT_MISFIRE_GRACE)
    ref = reference or now()
    return (ref - fire_time) <= grace


def _missed_fires_for_job(meta: dict, reference: Any) -> List[Any]:
    """Compute the list of missed fire times in (last_fired_at, reference].

    Returns tz-aware datetimes. Empty if none. Respects kind:
      - cron:    compute_missed_fires(cron, last_fired_or_created, reference)
      - interval: manual iteration last + interval, +interval, ... <= reference
      - once:    [run_at] if run_at <= reference and never fired, else []
    """
    kind = meta.get("kind", "")
    last_str = meta.get("last_fired_at", "") or meta.get("created_at", "")
    try:
        last = parse_iso(last_str) if last_str else reference
    except ValueError:
        last = reference

    if kind == "cron":
        try:
            return compute_missed_fires(meta["cron"], last, until=reference)
        except Exception:
            return []
    if kind == "interval":
        try:
            step = parse_duration(meta["interval"])
        except ValueError:
            return []
        fires: List[Any] = []
        t = last + step
        # Safety cap to avoid runaway on huge gaps (grace filtering happens next).
        cap = 10000
        while t <= reference and len(fires) < cap:
            fires.append(t)
            t = t + step
        return fires
    if kind == "once":
        if not meta.get("fire_if_missed", False):
            return []
        if meta.get("status") == "fired":
            return []
        try:
            run_at = parse_iso(meta["run_at"])
        except ValueError:
            return []
        if run_at <= reference:
            return [run_at]
        return []
    return []


def catch_up_missed_jobs(force: bool = False) -> dict:
    """Deliver any jobs that were due while the server was offline.

    Runs once per process (guarded by _catch_up_done) unless force=True. For
    each job in _job_registry:
      1. Compute missed fires in (last_fired_at, now].
      2. Drop fires older than the job's misfire_grace window.
      3. Apply the job's misfire_policy (skip / fire_last / fire_all).
      4. Update last_fired_at to now (idempotent — never re-process the same
         window on the next boot).

    Deliveries go through helpers._fire_job (which calls notify as the
    delivery backend), with catch_up=True so messages are stamped. Each
    catch-up delivery is logged via tracer + _log_delivery.

    Returns a summary dict: {checked, jobs_with_misses, fires_delivered,
    fires_skipped, policies_applied: {policy: count}}.

    This function is safe to call when the scheduler is not running — it
    only touches _job_registry + calls notify directly (not via APScheduler).
    """
    import sys
    from core.tracer import tracer
    global _catch_up_done
    with _catch_up_lock:
        if _catch_up_done and not force:
            return {"checked": 0, "note": "catch-up already run this process"}
        _catch_up_done = True

    tid = tracer.new_trace("schedule_catchup", goal="offline missed-fire recovery")
    reference = now()
    checked = 0
    jobs_with_misses = 0
    fires_delivered = 0
    fires_skipped = 0
    policies: Dict[str, int] = {}

    # Lazy import to avoid state→helpers circular import at module load.
    from tools.schedule_ops.helpers import _fire_job

    for job_id, meta in list(_job_registry.items()):
        checked += 1
        if meta.get("status") == "cancelled":
            continue
        policy = meta.get("misfire_policy", DEFAULT_MISFIRE_POLICY)
        if policy not in VALID_MISFIRE_POLICIES:
            policy = DEFAULT_MISFIRE_POLICY
        grace = meta.get("misfire_grace", DEFAULT_MISFIRE_GRACE) or DEFAULT_MISFIRE_GRACE

        try:
            missed = _missed_fires_for_job(meta, reference)
        except Exception as e:
            print(f"[catch_up] WARNING: job {job_id!r} missed-fire computation "
                  f"failed: {e}", file=sys.stderr)
            continue

        # Grace filtering: drop fires older than the grace window.
        missed = [ft for ft in missed if _within_grace(ft, grace, reference)]

        if not missed:
            continue
        jobs_with_misses += 1
        policies[policy] = policies.get(policy, 0) + 1

        tracer.step(tid, "schedule_catchup",
                    f"job {job_id!r}: {len(missed)} missed fires (policy={policy})")

        # Apply policy. once-jobs are gated by fire_if_missed (already filtered
        # in _missed_fires_for_job) — the policy trio does NOT apply to them;
        # if any missed fire survived, deliver it. cron/interval use the trio.
        to_fire: List[Any] = []
        if meta.get("kind") == "once":
            to_fire = list(missed)  # at most 1
        elif policy == "skip":
            to_fire = []
            fires_skipped += len(missed)
        elif policy == "fire_last":
            to_fire = [missed[-1]]
        elif policy == "fire_all":
            to_fire = missed[:MAX_FIRE_ALL]
            fires_skipped += max(0, len(missed) - MAX_FIRE_ALL)

        for ft in to_fire:
            try:
                _fire_job(job_id=job_id, fire_time=ft, catch_up=True)
                fires_delivered += 1
            except Exception as e:
                print(f"[catch_up] WARNING: delivery failed for job {job_id!r} "
                      f"@ {ft}: {e}", file=sys.stderr)

        # Idempotent: advance last_fired_at so we never re-process this window.
        # Use the most recent missed fire (or `reference` if skip) as the new
        # last_fired_at — accurate + prevents re-evaluation on next boot.
        new_last = missed[-1] if missed else reference
        mark_fired(job_id, new_last)

    summary = {
        "checked": checked,
        "jobs_with_misses": jobs_with_misses,
        "fires_delivered": fires_delivered,
        "fires_skipped": fires_skipped,
        "policies_applied": policies,
        "trace_id": tid,
    }
    tracer.finish(tid, success=True, result=str(summary))
    print(f"[schedule] catch-up complete: {summary}", file=sys.stderr)
    return summary


def reset_state() -> None:
    """Reset all module-level state. TEST-ONLY — never call in production.

    Called by the autouse fixture in conftest.py before each test.
    """
    global _scheduler, _catch_up_done
    with _scheduler_lock:
        if _scheduler is not None:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
            _scheduler = None
    with _catch_up_lock:
        _catch_up_done = False
    _job_registry.clear()
    _delivery_log.clear()
