"""
tools/notify.py — Notify meta-tool.

Replaces: old notify.py + scheduler.py (two separate tools → one)
The LLM sees ONE tool: notify(action, ...)

Actions:
  send     → desktop notification (cross-platform with graceful fallback)
  schedule → schedule a notification after N minutes (APScheduler)
  cancel   → cancel a scheduled notification
  list     → list all scheduled notifications

Cross-platform:
  Windows → plyer (native toast notifications)
  Linux   → notify-send (libnotify) if available, else print to console
  Fallback→ always prints to console so nothing is silently swallowed

STATUS SCHEMA NOTE:
 notify.py uses special status values that are semantically correct for
 notifications and are NOT mapped to the generic "success" value:
   "sent"      — immediate notification delivered
   "scheduled" — reminder queued for future delivery
   "ok"        — query/list operation succeeded
   "cancelled" — scheduled job removed
   "error"     — operation failed
 These are documented in ToolResult as valid notification-specific states.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from core.config import cfg
from registry import tool

# ── Scheduler singleton ───────────────────────────────────────────────────────

_scheduler: Any         = None
_scheduler_lock         = threading.Lock()
_job_registry: dict[str, dict] = {}


def _get_scheduler() -> Optional[Any]:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                _scheduler = BackgroundScheduler(daemon=True)
                _scheduler.start()
            except ImportError:
                return None
    return _scheduler


# ── Platform notification ─────────────────────────────────────────────────────

def _send_notification(title: str, message: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Send a desktop notification. Returns (success, method_used).
    Always falls back to console print — never silently fails.
    """
    # Windows — plyer
    if cfg.is_windows:
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="MCP Agent",
                timeout=timeout,
            )
            return True, "plyer"
        except Exception:
            pass  # fall through to console

    # Linux — notify-send
    if not cfg.is_windows:
        try:
            import subprocess
            result = subprocess.run(
                ["notify-send", "-t", str(timeout * 1000), title, message],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True, "notify-send"
        except (FileNotFoundError, Exception):
            pass  # fall through to console

    # Universal fallback — console print
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[NOTIFY {ts}] {title}: {message}\n", file=sys.stderr)
    return True, "console"


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def notify(
    action:        str,
    title:         str = "",
    message:       str = "",
    timeout:       int = 5,
    delay_minutes: int = 0,
    job_id:        str = "",
) -> dict:
    """
    Notification tool — send desktop alerts and schedule reminders.

    action: "send" | "schedule" | "cancel" | "list"

    send
        Send an immediate desktop notification.
        Required: message
        Optional: title (default "Agent"), timeout (seconds, default 5)
        Returns:  {status, method}

    schedule
        Schedule a notification after a delay.
        Required: message, delay_minutes
        Optional: title
        Returns:  {status, job_id, run_at}

    cancel
        Cancel a scheduled notification.
        Required: job_id (from schedule response)
        Returns:  {status, job_id}

    list
        List all scheduled notifications.
        Returns:  {jobs: [{job_id, run_at, title, message}], count}

    Examples:
        notify(action="send", title="Research done", message="Tesla analysis complete")
        notify(action="schedule", message="Check autocode results", delay_minutes=10)
        notify(action="cancel", job_id="reminder_1234567890")
        notify(action="list")
    """
    action = action.strip().lower()

    # ── send ──────────────────────────────────────────────────────────────────
    if action == "send":
        if not message:
            return {"status": "error", "error": "message is required for send"}

        send_title  = title or "Agent"
        ok, method  = _send_notification(send_title, message, timeout)

        return {
            "status":  "sent" if ok else "error",
            "title":   send_title,
            "message": message,
            "method":  method,
        }

    # ── schedule ──────────────────────────────────────────────────────────────
    if action == "schedule":
        if not message:
            return {"status": "error", "error": "message is required for schedule"}
        if delay_minutes <= 0:
            return {"status": "error", "error": "delay_minutes must be > 0 for schedule"}

        scheduler = _get_scheduler()
        if scheduler is None:
            return {
                "status": "error",
                "error":  "APScheduler not installed. Run: pip install apscheduler",
            }

        try:
            from apscheduler.triggers.date import DateTrigger

            run_time   = datetime.now() + timedelta(minutes=delay_minutes)
            job_id_new = f"reminder_{int(time.time())}"
            send_title = title or "Agent Reminder"

            scheduler.add_job(
                func=_send_notification,
                trigger=DateTrigger(run_date=run_time),
                kwargs={"title": send_title, "message": message},
                id=job_id_new,
            )

            _job_registry[job_id_new] = {
                "title":   send_title,
                "message": message,
                "run_at":  run_time.isoformat(),
                "status":  "scheduled",
            }

            return {
                "status":        "scheduled",
                "job_id":        job_id_new,
                "message":       message,
                "run_at":        run_time.strftime("%Y-%m-%d %H:%M:%S"),
                "delay_minutes": delay_minutes,
            }

        except Exception as e:
            return {"status": "error", "error": f"Schedule failed: {e}"}

    # ── cancel ────────────────────────────────────────────────────────────────
    if action == "cancel":
        if not job_id:
            return {"status": "error", "error": "job_id is required for cancel"}

        scheduler = _get_scheduler()
        if scheduler is None:
            return {"status": "error", "error": "Scheduler not running"}

        try:
            scheduler.remove_job(job_id)
            _job_registry.pop(job_id, None)
            return {"status": "cancelled", "job_id": job_id}
        except Exception as e:
            return {"status": "error", "error": f"Cancel failed: {e} (job may already have run)"}

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        scheduler = _get_scheduler()
        if scheduler is None:
            return {"status": "ok", "jobs": [], "count": 0, "note": "Scheduler not running"}

        try:
            jobs = scheduler.get_jobs()
            result = []
            for job in jobs:
                meta = _job_registry.get(job.id, {})
                result.append({
                    "job_id":  job.id,
                    "run_at":  str(job.next_run_time),
                    "title":   meta.get("title", ""),
                    "message": meta.get("message", ""),
                })
            return {"status": "ok", "jobs": result, "count": len(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    return {
        "status": "error",
        "error":  f"Unknown action '{action}'. Use: send | schedule | cancel | list",
    }
