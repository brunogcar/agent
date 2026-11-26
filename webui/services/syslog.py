"""webui/services/syslog.py — the in-app system log (the 📜 drawer's data).

[v1.20] "What is going on inside the WebUI" — the terminal tail made
visible in-app. FOUR capture paths feed ONE ring buffer:

  1. RequestLoggingMiddleware (pure ASGI, streaming-safe — no
     BaseHTTPMiddleware, so SSE responses pass through untouched):
     method + path + QUERY STRING + status + duration for every
     non-static request. 4xx → warning, 5xx/exceptions → error,
     everything else → info. OPTIONS preflights and /static/ assets are
     skipped (noise). [v1.28.1] the query string rides along (the
     `_t=` cache-buster stripped) — `?q=pomo4` says much more than a
     bare /tools/comparison/search.
  2. RingBufferHandler on the ROOT Python logger (WARNING+): unhandled
     ASGI exceptions, library warnings — anything that already goes
     through ``logging`` shows up here too. [v1.28.1] the handler ALSO
     attaches to the "uvicorn"/"uvicorn.error" loggers at INFO — the
     startup/shutdown banner lines the terminal prints ("Application
     startup complete", "Shutting down") land in the drawer too.
     uvicorn.access records are still skipped (the middleware already
     logs requests with a duration; double lines would be pure noise).
  3. Explicit ``syslog.log()`` calls: sync job lifecycle (started /
     completed / failed / per-ticker bulk progress), startup freshness
     check, settings changes, the auto-sync scheduler.
  4. [v1.28.1] StdoutTee on sys.stdout + sys.stderr: EVERY print() the
     process emits — the "[ratios] 12/49 roe (0.00s) = 0.58" progress
     lines, the "[webui] screener POMO4 partial: …" degradation notes,
     engine tracebacks — lands in the drawer with a parsed source badge
     (ratios / webui / app / stderr). The user's ask: "log do sistema
     doesnt display powershell logs… is just display info like GET …
     → 200 · 7ms". The tee is line-buffered (partial writes coalesce),
     thread-safe, reentrancy-guarded and idempotent; the original
     stream keeps receiving every byte (PowerShell looks the same).

Consumed by ``GET /api/webui/logs`` (snapshot/since) and
``GET /api/webui/logs/stream`` (SSE: one snapshot event + 1s polls —
no subscriber registry needed; the SyncService SSE pub/sub exists because
WORKER THREADS push, here the buffer is pulled).

Behavior notes:
  - In-memory ONLY, per process: it is a tail, not a log file. Restart
    clears it (that's the point — "what happened since I opened it").
  - min level + buffer size come from the SettingsService (logs.level /
    logs.buffer) and apply LIVE — the buffer is re-trimmed on the next
    append, the level on the next log() call.
  - Entry ids are monotonic per process; the client dedupes with
    ``since(id)`` semantics across reconnects.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from webui.services.settings import settings_service

_LEVELS = {"info": 0, "warning": 1, "error": 2}
_MAX_MSG = 600  # tracebacks get truncated — the panel is a tail, not a dump


class SystemLog:
    """Thread-safe in-memory log ring buffer."""

    def __init__(self) -> None:
        # [v1.22.1] RLock (B118): reentrant — a future log() call from
        # inside a locked helper (or a settings callback while the lock
        # is held) would deadlock on a plain Lock.
        self._lock = threading.RLock()
        self._buf: deque[dict[str, Any]] = deque(maxlen=500)
        self._next_id = 1
        # [v1.28.2] the day the buffer is currently on (None → the first
        # log() opens with a date separator; a midnight crossing adds one).
        self._cur_date = None

    # ── configuration (live, from settings) ──────────────────────────────────

    @staticmethod
    def _min_level() -> int:
        return _LEVELS.get(
            settings_service().get("logs.level", "info"), 0)

    def _buffer_size(self) -> int:
        """logs.buffer clamped to [100, 5000] — a settings READ, so the
        [v1.22.1] rule is: call this with NO syslog lock held."""
        size = settings_service().get("logs.buffer", 500)
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 500
        return max(100, min(5000, size))

    def _retrim(self, size: int) -> None:
        """Apply a logs.buffer change (caller holds the lock)."""
        if self._buf.maxlen != size:
            self._buf = deque(self._buf, maxlen=size)

    # ── write ────────────────────────────────────────────────────────────────

    def log(self, level: str, source: str, message: str) -> None:
        """Append one entry (thread-safe; drops below the min level).

        [v1.28.2] When the calendar day changes mid-session, a
        ``── dd/mm/aaaa ──`` separator lands first (and the buffer opens
        with one): the tail's timestamps are time-only, so without it the
        23:59 and the 00:01 lines look like the same day forever.
        """
        if _LEVELS.get(level, 0) < self._min_level():
            return
        msg = str(message).replace("\n", " ")[:_MAX_MSG]
        # [v1.22.1] B118: EVERY settings read happens BEFORE the syslog
        # lock is taken (_min_level above, _buffer_size here) — the syslog
        # lock is never held across a settings-lock acquisition, so no
        # lock ordering between the two services can be armed into a
        # cross-lock deadlock (both locks are RLock for reentrancy).
        size = self._buffer_size()
        now = datetime.now()
        with self._lock:
            self._retrim(size)
            if now.date() != self._cur_date:
                self._cur_date = now.date()
                self._buf.append({
                    "id": self._next_id,
                    "ts": now.strftime("%H:%M:%S"),
                    "level": "info",
                    "source": "webui",
                    "message": f"── {now.strftime('%d/%m/%Y')} ──",
                })
                self._next_id += 1
            self._buf.append({
                "id": self._next_id,
                "ts": now.strftime("%H:%M:%S"),
                "level": level if level in _LEVELS else "info",
                "source": str(source)[:24] or "webui",
                "message": msg,
            })
            self._next_id += 1

    # ── read ─────────────────────────────────────────────────────────────────

    def snapshot(self, limit: int = 300) -> list[dict[str, Any]]:
        """The last ``limit`` entries (oldest first)."""
        with self._lock:
            entries = list(self._buf)
        return entries[-max(1, min(limit, 5000)):]

    def since(self, after_id: int) -> list[dict[str, Any]]:
        """Entries with id > after_id (oldest first; empty list = nothing)."""
        with self._lock:
            return [e for e in self._buf if e["id"] > after_id]


# ── module-level singleton ────────────────────────────────────────────────────
syslog = SystemLog()


# ── capture path 2: Python logging → ring buffer ─────────────────────────────
class RingBufferHandler(logging.Handler):
    """Root-logger handler: WARNING+ records land in the drawer.

    uvicorn.access is skipped (the request middleware already logs those,
    with a duration); uvicorn.error tracebacks ("Exception in ASGI
    application") are the main thing this path catches. [v1.28.1] The
    same handler class attaches to "uvicorn"/"uvicorn.error" at INFO —
    those loggers don't propagate to the root, and their startup banner
    lines are part of "what the terminal shows".
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            if record.name.startswith("uvicorn.access"):
                return
            level = ("error" if record.levelno >= logging.ERROR
                     else "warning" if record.levelno >= logging.WARNING
                     else "info")
            extra = ""
            if record.exc_info and record.exc_info[0] is not None:
                extra = f" ({record.exc_info[0].__name__})"
            source = "uvicorn" if record.name.startswith("uvicorn") else "py"
            syslog.log(level, source,
                       f"{record.name}: {record.getMessage()}{extra}")
        except Exception:
            # A logging handler must never take the app down.
            pass


def attach_logging_handler() -> None:
    """Idempotently attach the ring-buffer handler to the root logger
    (WARNING+) AND to the uvicorn loggers (INFO — startup/shutdown
    banners; uvicorn.access stays skipped inside emit)."""
    root = logging.getLogger()
    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        handler = RingBufferHandler()
        handler.setLevel(logging.WARNING)
        root.addHandler(handler)
    # [v1.28.1] uvicorn's own loggers don't reach the root — hook them
    # directly so the terminal's startup/shutdown lines show in-app too.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(h, RingBufferHandler) for h in logger.handlers):
            handler = RingBufferHandler()
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)


# ── capture path 4 [v1.28.1]: print() tee → ring buffer ──────────────────────
class _StdoutTee:
    """Line-buffered wrapper around sys.stdout / sys.stderr.

    Every complete line written to the wrapped stream is ALSO appended to
    the ring buffer, tagged by what the line looks like:

      "[ratios] 12/49 roe (0.00s) = 0.58"  → source "ratios" (info)
      "[webui] screener POMO4 partial: …"  → source "webui" (warning on
                                             "failed", error on
                                             "Traceback")
      anything else on stdout              → source "app" (info)
      anything else on stderr              → source "stderr" (warning;
                                             error on "Traceback")

    The original stream receives every byte first (PowerShell output is
    unchanged). ``_guard`` (thread-local [v1.28.2]) stops re-entrant
    captures — a print from inside syslog internals must not loop, but
    prints from OTHER threads keep flowing (the old process-wide flag
    silently dropped them while one capture ran). Thread-safe: ``_lock``
    owns the partial-line buffer (interleaved prints from worker threads
    never merge two half-lines). Everything but write/writelines/flush
    delegates to the original stream (isatty, encoding, fileno…).
    """

    _MAX_LINE = 600  # same tail-not-dump cap as SystemLog.log

    def __init__(self, original, is_stderr: bool) -> None:
        self._original = original
        self._is_stderr = is_stderr
        self._lock = threading.Lock()
        self._pending = ""
        # [v1.28.2] the reentrancy guard is THREAD-LOCAL now: the old
        # process-wide flag made a print() from ANY other thread land in
        # the bit bucket while one capture ran (two worker threads
        # printing at once = one line missing from the drawer). Prints
        # re-entering from the CAPTURING thread are still swallowed
        # (that's the loop protection); everyone else buffers normally.
        self._guard = threading.local()

    # ── stream API ──
    def write(self, text) -> int:
        try:
            try:
                n = self._original.write(text)
            except Exception:
                n = len(text) if text else 0
            self._capture(text)
            return n
        except Exception:
            return len(text) if text else 0

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):  # isatty, encoding, fileno, buffer…
        return getattr(self._original, name)

    # ── capture ──
    def _capture(self, text) -> None:
        if not text or getattr(self._guard, "busy", False):
            return
        try:
            self._guard.busy = True
            with self._lock:
                self._pending += str(text)
                lines = self._pending.split("\n")
                self._pending = lines.pop()  # last = partial (or "")
            for line in lines:
                line = line.rstrip("\r").strip()
                if line:
                    self._emit(line[: self._MAX_LINE])
        except Exception:
            pass  # a log tee must never take the app down
        finally:
            self._guard.busy = False

    def _emit(self, line: str) -> None:
        low = line.lower()
        if "[ratios]" in low:
            source, level = "ratios", "info"
        elif line.startswith("[webui]") or low.startswith("[webui]"):
            source = "webui"
            level = ("error" if "traceback" in low
                     else "warning" if "failed" in low else "info")
        elif self._is_stderr:
            source = "stderr"
            level = "error" if "traceback" in low else "warning"
        else:
            source, level = "app", "info"
        syslog.log(level, source, line)


def attach_print_tee() -> None:
    """Idempotently wrap sys.stdout + sys.stderr in _StdoutTee."""
    for stream, is_stderr in ((sys.stdout, False), (sys.stderr, True)):
        if stream is None:
            continue
        if isinstance(stream, _StdoutTee):
            continue
        try:
            setattr(sys, "stderr" if is_stderr else "stdout",
                    _StdoutTee(stream, is_stderr))
        except Exception:
            pass  # never block startup on a logging concern


# ── capture path 1: pure ASGI request middleware ─────────────────────────────
# NOT BaseHTTPMiddleware: that wraps responses in a way that interferes with
# long-lived SSE streams (and this app leans on SSE twice). A raw ASGI
# wrapper adds ~15 lines and streams untouched.
class RequestLoggingMiddleware:
    """Log every HTTP request (method, path, status, duration) to syslog."""

    # Paths that never show up (assets, docs, CORS preflights).
    # [v1.22.1] B127: /api/webui/logs is in the list too — the log
    # endpoints were capturing THEMSELVES (every drawer poll appended
    # "GET /api/webui/logs → 200", so watching the log spammed the log;
    # the /stream SSE open line went the same way — prefix covers both).
    _SKIP_PREFIXES = ("/static/", "/favicon", "/docs", "/openapi.json",
                      "/api/webui/logs")
    _SKIP_METHODS = ("OPTIONS", "HEAD")

    def __init__(self, app) -> None:
        self.app = app

    @staticmethod
    def _path_with_query(scope) -> str:
        """[v1.28.1] path + the MEANINGFUL query string — the `_t=`
        cache-buster is stripped, anything else (?q=pomo4, ?ticker=POMO4)
        rides along ("i want that log to display more info")."""
        path = scope.get("path", "?")
        qs = (scope.get("query_string") or b"").decode("latin-1", "replace")
        if qs:
            import re as _re
            qs = _re.sub(r"(^|&)_t=\d+", r"\1", qs).strip("&")
        return f"{path}?{qs}" if qs else path

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        if method in self._SKIP_METHODS or path.startswith(self._SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        # SSE endpoints stay open for minutes — log the OPEN, not the close
        # (the completion line would only appear when the drawer disconnects).
        if path.endswith("/stream"):
            syslog.log("info", "http",
                       f"{method} {self._path_with_query(scope)} · SSE aberto")
            await self.app(scope, receive, send)
            return

        state = {"status": 0}
        start = time.perf_counter()

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            elapsed = _fmt_ms(time.perf_counter() - start)
            syslog.log("error", "http",
                       f"{method} {self._path_with_query(scope)} → exceção "
                       f"({type(e).__name__}) · {elapsed}")
            raise
        else:
            status = state["status"]
            elapsed = _fmt_ms(time.perf_counter() - start)
            level = ("error" if status >= 500
                     else "warning" if status >= 400
                     else "info")
            syslog.log(level, "http",
                       f"{method} {self._path_with_query(scope)} → {status} · {elapsed}")


def _fmt_ms(seconds: float) -> str:
    """Duration for the log line: '12ms' / '1,4s' (pt-BR comma)."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)}ms"
    return f"{seconds:.1f}".replace(".", ",") + "s"
