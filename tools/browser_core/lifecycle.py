"""Lifecycle management: reaper thread, cleanup, and screenshot pruning."""
from __future__ import annotations

import atexit
import logging
import threading
import time
from pathlib import Path
from typing import Any

from core.config import cfg
from tools.browser_core import state as _st
from tools.browser_core.loop import _run_browser_async

logger = logging.getLogger(__name__)

_SCREENSHOT_MAX_AGE_DAYS = 7


def _cleanup_old_screenshots() -> int:
    """Delete screenshot files older than _SCREENSHOT_MAX_AGE_DAYS.

    Returns number of files deleted.
    """
    try:
        screenshot_dir = cfg.workspace_root / "screenshots"
    except Exception:
        return 0
    if not screenshot_dir.exists():
        return 0

    cutoff = time.time() - (_SCREENSHOT_MAX_AGE_DAYS * 86400)
    deleted = 0
    try:
        for f in screenshot_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    deleted += 1
                except OSError:
                    pass
        if deleted > 0:
            logger.info("[browser] Cleaned up %d old screenshots", deleted)
    except OSError:
        pass
    return deleted


def _start_reaper():
    """Start background daemon threads:
    1. Close idle browser contexts after 10 minutes.
    2. Clean up old screenshot files periodically.
    """
    if _st._reaper_started:
        return
    _st._reaper_started = True

    # Clean up old screenshots on startup — swallow errors so browser can still start
    try:
        _cleanup_old_screenshots()
    except Exception:
        pass

    def _reap():
        while True:
            time.sleep(60)
            now = time.time()
            to_close = []
            with _st._browser_lock:
                for tid, (ctx, last_used) in list(_st._contexts.items()):
                    if now - last_used > 600:  # 10 minutes idle
                        to_close.append((tid, ctx))
                for tid, _ in to_close:
                    if tid in _st._pages:
                        del _st._pages[tid]
                    del _st._contexts[tid]
                for tid, ctx in to_close:
                    try:
                        _run_browser_async(ctx.close(), timeout=30)
                    except Exception:
                        pass
                    logger.info("[browser] Reaped idle context for trace %s", tid)

            # Periodic screenshot cleanup (every ~6 hours = 360 cycles of 60s)
            if int(now) % 21600 < 60:
                try:
                    _cleanup_old_screenshots()
                except Exception:
                    pass

    t = threading.Thread(target=_reap, daemon=True, name="browser-reaper")
    t.start()


def _cleanup_all():
    """Close all browser resources. Called on process exit."""
    with _st._browser_lock:
        for tid in list(_st._pages.keys()):
            _st._pages.pop(tid, None)
        for tid, (ctx, _) in list(_st._contexts.items()):
            try:
                _run_browser_async(ctx.close(), timeout=30)
            except Exception:
                pass
            _st._contexts.pop(tid, None)
        if _st._browser:
            try:
                _run_browser_async(_st._browser.close(), timeout=30)
            except Exception:
                pass
            _st._browser = None
        if _st._playwright:
            try:
                _run_browser_async(_st._playwright.stop(), timeout=30)
            except Exception:
                pass
            _st._playwright = None


# Register atexit handler for normal process shutdown
atexit.register(_cleanup_all)
