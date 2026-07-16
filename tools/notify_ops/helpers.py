"""tools/notify_ops/helpers.py — Shared utilities for notify actions.

Extracted from the original tools/notify.py during the v1.0 @meta_tool
refactor. Two responsibilities:

  1. _get_scheduler() — lazy APScheduler singleton + persistence reload.
  2. _send_notification() — cross-platform desktop notification with
     graceful fallback chain (plyer → notify-send → console).

[DESIGN] KEY INVARIANTS — read before modifying:
  1. _get_scheduler() is the ONLY entry point to the _scheduler singleton.
     Action handlers must NEVER touch state._scheduler directly. The
     function is idempotent: first call initializes + starts the scheduler
     + loads persisted jobs; subsequent calls return the cached instance.

  2. APScheduler is a HARD dependency for schedule/recurring/cancel/list
     actions. _get_scheduler() returns None on ImportError so callers can
     produce a graceful "APScheduler not installed" error instead of
     crashing. send/test/history do NOT need APScheduler and work even
     when it's unavailable.

  3. _send_notification() ALWAYS returns (success_bool, method_str) and
     ALWAYS succeeds via the console fallback. The fallback prints to
     stderr so notifications are never silently swallowed. After every
     delivery attempt, _log_delivery() is called to record the event
     for the `history` action — even on fallback (the LLM may want to
     know "we delivered, but only to console because plyer crashed").

  4. The platform detection chain is identical to the original notify.py:
       Windows → plyer (native toast)
       Linux   → notify-send (libnotify) if available
       Fallback→ console print (stderr)
     We deliberately do NOT short-circuit on the first success — if
     plyer raises, we fall through to notify-send on Windows too? No:
     the `if cfg.is_windows` / `if not cfg.is_windows` branches are
     mutually exclusive (one branch per OS), and within each branch
     failures fall through to the universal console fallback. This
     matches the original tool's behavior exactly.

  5. We import state lazily inside _send_notification to avoid a circular
     import: state.py imports helpers._send_notification for the
     _noop_fire stub, so helpers.py must NOT import state.py at module
     level. The lazy import inside the function body breaks the cycle.
"""
from __future__ import annotations

import sys
from typing import Optional, Tuple

from core.time_utils import now, format_dt

from core.config import cfg

import threading as _threading


def _get_scheduler() -> Optional[object]:
    """Return the singleton BackgroundScheduler, initializing on first call.

    Returns None if APScheduler is not installed — callers must handle this
    case with a graceful error. On first successful initialization:
      1. Create BackgroundScheduler(daemon=True).
      2. Start it (background thread).
      3. Call state._load_jobs() to reload persisted job registry.

    Thread-safe via state._scheduler_lock.
    """
    # Lazy import to avoid state.py ↔ helpers.py circular import at module
    # load time. state.py imports _send_notification from helpers for the
    # _noop_fire stub, so helpers.py must NOT import state at top level.
    from tools.notify_ops import state

    global _scheduler_ref  # not used; we go through state._scheduler

    with state._scheduler_lock:
        if state._scheduler is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                sched = BackgroundScheduler(daemon=True)
                sched.start()
                state._scheduler = sched
                # Reload persisted jobs AFTER scheduler is running so
                # _load_jobs can re-add them via sched.add_job().
                state._load_jobs()
            except ImportError:
                return None
        return state._scheduler


def _send_notification(title: str, message: str, timeout: int = 5) -> Tuple[bool, str]:
    """Send a desktop notification. Returns (success, method_used).

    Always falls back to console print — never silently fails. After every
    delivery (success or fallback), _log_delivery() is called to record
    the event in state._delivery_log for the `history` action.

    Platform chain:
      Windows → plyer (native toast)
      Linux   → notify-send (libnotify) if available
      Fallback→ console print to stderr

    The `timeout` param controls how long the toast shows (ms on Linux,
    seconds on Windows plyer). Always returns success=True because the
    console fallback cannot fail.
    """
    method: str = ""
    success: bool = False

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
            method, success = "plyer", True
        except Exception:
            pass  # fall through to console

    # Linux — notify-send
    if not cfg.is_windows and not success:
        try:
            import subprocess
            result = subprocess.run(
                ["notify-send", "-t", str(timeout * 1000), title, message],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                method, success = "notify-send", True
        except (FileNotFoundError, Exception):
            pass  # fall through to console

    # Universal fallback — console print to stderr
    if not success:
        ts = format_dt(now(), "%H:%M:%S")
        print(f"\n[NOTIFY {ts}] {title}: {message}\n", file=sys.stderr)
        method, success = "console", True

    # Log the delivery (lazy import to break state ↔ helpers cycle).
    try:
        from tools.notify_ops import state
        state._log_delivery(title=title, message=message, method=method)
    except Exception:
        # Best-effort — never crash on logging failure.
        pass

    return success, method
