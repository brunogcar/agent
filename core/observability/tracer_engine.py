# core/observability/tracer_engine.py -- Structured logging and trace ID propagation.
"""Structured logging and trace ID propagation.

CRITICAL: This module must NEVER write to stdout.
In MCP stdio transport mode stdout is the protocol channel.
Any non-JSON-RPC bytes on stdout corrupt the connection.

All output goes to:
 - stderr (structlog console output)
 - logs/agent_YYYYMMDD.jsonl (file, always)

Usage:
 from core.tracer import tracer

 tid = tracer.new_trace("autocode", goal="fix memory.py")
 tracer.step(tid, "read ", "file loaded ", chars=4200)
 tracer.error(tid, "apply ", "patch failed ", error="context mismatch")
 tracer.finish(tid, success=True, result="committed abc123")
 trace = tracer.get(tid)
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
import atexit
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from core.config import cfg

# Optional structlog support with graceful fallback
try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False
    # Fallback to standard logging if structlog not available
    import logging
    logging.basicConfig(
        level=logging.DEBUG if cfg.autocode_debug else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

# -- Trace ID generator (LOW-05) --------------------------------------------
def generate_trace_id(length: int = 12) -> str:
    """Return a short hex trace ID, e.g. 'a3f2c0b1'."""
    return uuid.uuid4().hex[:length]

# -- structlog: write to STDERR only -----------------------------------------
def _configure_structlog() -> None:
    """Configure structlog for stderr output only. Never touches stdout."""
    if not _HAS_STRUCTLOG:
        return  # Skip if structlog not available

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            10 if cfg.autocode_debug else 20
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

_configure_structlog()

if _HAS_STRUCTLOG:
    _log = structlog.get_logger()
else:
    _log = logging.getLogger("agent")

# -- File log writer ---------------------------------------------------------
class _FileWriter:
    """Thread-safe JSONL log writer. Writes to disk only -- never stdout."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_date: str = ""
        self._file: Optional[Any] = None

    def _get_file(self) -> Any:
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date or self._file is None:
            if self._file:
                self._file.close()
            cfg.agent_log_path.mkdir(parents=True, exist_ok=True)
            log_file = cfg.agent_log_path / f"agent_{today}.jsonl"
            self._file = open(log_file, "a", encoding="utf-8")
            self._current_date = today
        return self._file

    def write(self, record: dict) -> None:
        with self._lock:
            try:
                f = self._get_file()
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            except (KeyboardInterrupt, SystemExit):
                raise  # never suppress shutdown signals
            except Exception:
                pass  # non-fatal I/O errors silently ignored

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None

_writer = _FileWriter()

# [P2 FIX] Register file writer close at process exit.
# Ensures the JSONL log file is properly flushed and closed
# on normal termination, preventing truncated last entries.
atexit.register(_writer.close)

# -- Trace store -------------------------------------------------------------
class _TraceStore:
    """In-memory store for active traces. Bounded to prevent memory leak."""
    MAX_TRACES = 200

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, dict] = {}
        self._order: list[str] = []

    def create(self, trace_id: str, record: dict) -> None:
        with self._lock:
            self._store[trace_id] = record
            self._order.append(trace_id)
            while len(self._order) > self.MAX_TRACES:
                old_id = self._order.pop(0)
                self._store.pop(old_id, None)

    def get(self, trace_id: str) -> Optional[dict]:
        with self._lock:
            return self._store.get(trace_id)

    def update(self, trace_id: str, key: str, value: Any) -> None:
        with self._lock:
            if trace_id in self._store:
                self._store[trace_id][key] = value

    def append_step(self, trace_id: str, step: dict) -> None:
        with self._lock:
            if trace_id in self._store:
                self._store[trace_id].setdefault("steps", []).append(step)

    def all_recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            recent_ids = self._order[-n:]
            return [self._store[tid] for tid in reversed(recent_ids)
                    if tid in self._store]

_store = _TraceStore()

# -- Public Tracer -----------------------------------------------------------
class Tracer:
    """
    Structured tracer for agent workflows.
    Thread-safe. All output goes to stderr + log file. Never stdout.
    """
    def new_trace(self, workflow: str, goal: str = "", **kwargs: Any) -> str:
        trace_id = generate_trace_id()
        ts = time.time()
        # [P0 FIX] kwargs spread FIRST so hardcoded keys cannot be overwritten.
        # Consistent with step(), error(), warning(), finish() fixes.
        record = {
            **kwargs,
            "trace_id": trace_id,
            "workflow": workflow,
            "goal": goal,
            "started_at": ts,
            "started_fmt": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "steps": [],
        }
        _store.create(trace_id, record)
        _writer.write({**record, "event": "trace_start"})
        # stderr only -- never stdout
        print(
            json.dumps({
                "trace_id": trace_id, "workflow": workflow,
                "goal": goal, "event": "trace_start",
                "level": "info",
                "timestamp": datetime.fromtimestamp(ts).isoformat(),
            }),
            file=sys.stderr,
        )
        return trace_id

    def step(self, trace_id: str, node: str, message: str = "",
             **kwargs: Any) -> None:
        ts = time.time()
        # Defensive: kwargs spread FIRST so hardcoded keys can't be accidentally overwritten.
        # This prevents bugs like passing event="task_not_found" which would corrupt the event field.
        entry = {
            **kwargs,
            "event": "step",
            "trace_id": trace_id,
            "node": node,
            "message": message,
            "ts": ts,
            "latency_ms": kwargs.get("latency_ms"),
        }
        _store.append_step(trace_id, entry)
        _writer.write(entry)
        if cfg.autocode_debug:  # <-- now inside step()
            if _HAS_STRUCTLOG:
                _log.debug("step", trace_id=trace_id, node=node, msg=message[:120])
            else:
                _log.debug(f"[step] {trace_id} | {node} | {message[:120]}")

    def error(self, trace_id: str, node: str, message: str = "",
              **kwargs: Any) -> None:
        ts = time.time()
        # Defensive: kwargs spread FIRST so hardcoded keys can't be accidentally overwritten.
        # This prevents bugs like passing event="task_not_found" which would corrupt the event field.
        entry = {
            **kwargs,
            "event": "error",
            "trace_id": trace_id,
            "node": node,
            "message": message,
            "ts": ts,
        }
        _store.append_step(trace_id, entry)
        _writer.write(entry)
        if _HAS_STRUCTLOG:
            _log.warning("error", trace_id=trace_id, node=node, msg=message[:200])
        else:
            _log.warning(f"[error] {trace_id} | {node} | {message[:200]}")

    def warning(self, trace_id: str, node: str, message: str = "",
                **kwargs: Any) -> None:
        """Log a warning-level event with trace context. Follows same pattern as error()."""
        ts = time.time()
        # Defensive: kwargs spread FIRST so hardcoded keys can't be accidentally overwritten.
        # This prevents bugs like passing event="task_not_found" which would corrupt the event field.
        entry = {
            **kwargs,
            "event": "warning",
            "trace_id": trace_id,
            "node": node,
            "message": message,
            "ts": ts,
        }
        _store.append_step(trace_id, entry)
        _writer.write(entry)
        if _HAS_STRUCTLOG:
            _log.warning("warning", trace_id=trace_id, node=node, msg=message[:200])
        else:
            _log.warning(f"[warning] {trace_id} | {node} | {message[:200]}")

    def finish(self, trace_id: str, success: bool = True,
               result: str = "", **kwargs: Any) -> None:
        ts = time.time()
        trace = _store.get(trace_id)
        elapsed = round(ts - trace["started_at"], 2) if trace else 0.0
        # [P0 FIX] kwargs spread FIRST so hardcoded keys can't be accidentally overwritten.
        # Consistent with step(), error(), warning() fixes above.
        entry = {
            **kwargs,
            "event": "trace_finish",
            "trace_id": trace_id,
            "success": success,
            "result": result[:200],
            "elapsed_s": elapsed,
            "ts": ts,
        }
        _store.update(trace_id, "status", "success" if success else "failed")
        _store.update(trace_id, "elapsed", elapsed)
        _store.update(trace_id, "result", result[:200])
        _store.append_step(trace_id, entry)
        _writer.write(entry)
        # stderr only
        if _HAS_STRUCTLOG:
            _log.info("trace_finish",
                      trace_id=trace_id,
                      status="success" if success else "failed",
                      elapsed=f"{elapsed}s")
        else:
            _log.info(f"[trace_finish] {trace_id} | status={'success' if success else 'failed'} | elapsed={elapsed}s")

    def get(self, trace_id: str) -> Optional[dict]:
        return _store.get(trace_id)

    def recent(self, n: int = 10) -> list[dict]:
        return _store.all_recent(n)

    def summary(self, trace_id: str) -> str:
        trace = _store.get(trace_id)
        if not trace:
            return f"trace {trace_id} not found"
        status = trace.get("status", "unknown")
        elapsed = trace.get("elapsed", 0)
        steps = len(trace.get("steps", []))
        goal = trace.get("goal", "")[:60]
        return (
            f"[{trace_id}] {trace['workflow']} | "
            f"goal={goal!r} | status={status} | "
            f"steps={steps} | elapsed={elapsed}s"
        )

# -- Singleton ---------------------------------------------------------------
tracer = Tracer()
