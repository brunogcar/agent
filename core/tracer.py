"""
core/tracer.py — Structured logging and trace ID propagation.

Every workflow run, tool call, and agent invocation gets a trace_id.
That ID flows through the entire execution so failures can be reconstructed.

Usage:
    from core.tracer import tracer

    # Start a new trace (returns the trace_id)
    tid = tracer.new_trace("autocode", goal="fix memory.py")

    # Log steps within that trace
    tracer.step(tid, "read",    "file loaded", chars=4200)
    tracer.step(tid, "analyze", "calling executor")
    tracer.error(tid, "apply",  "patch failed", error="context mismatch")

    # Mark trace complete
    tracer.finish(tid, success=True, result="committed abc123")

    # Get full trace for debugging
    trace = tracer.get(tid)

Logs are written as structured JSON to:
    D:/mcp/agent/logs/agent_YYYYMMDD.jsonl

The LLM never sees tracer internals — it's purely for debugging.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from core.config import cfg


# ── structlog configuration ───────────────────────────────────────────────────

def _configure_structlog() -> None:
    """Configure structlog for JSON output to file + readable output to console."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            10 if cfg.autocode_debug else 20  # DEBUG if debug mode, else INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

_configure_structlog()
_log = structlog.get_logger()


# ── File log writer ───────────────────────────────────────────────────────────

class _FileWriter:
    """Thread-safe JSONL log writer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_date: str = ""
        self._file: Optional[Any] = None

    def _get_file(self) -> Any:
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date or self._file is None:
            if self._file:
                self._file.close()
            cfg.log_path.mkdir(parents=True, exist_ok=True)
            log_file = cfg.log_path / f"agent_{today}.jsonl"
            self._file = open(log_file, "a", encoding="utf-8")
            self._current_date = today
        return self._file

    def write(self, record: dict) -> None:
        with self._lock:
            try:
                f = self._get_file()
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            except Exception:
                pass  # never crash the agent over a log write

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None


_writer = _FileWriter()


# ── Trace store ───────────────────────────────────────────────────────────────

class _TraceStore:
    """In-memory store for active traces. Bounded to prevent memory leak."""

    MAX_TRACES = 200

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._store: dict[str, dict] = {}
        self._order: list[str]       = []  # insertion order for eviction

    def create(self, trace_id: str, record: dict) -> None:
        with self._lock:
            self._store[trace_id] = record
            self._order.append(trace_id)
            # Evict oldest if over limit
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
            return [self._store[tid] for tid in reversed(recent_ids) if tid in self._store]


_store = _TraceStore()


# ── Public Tracer class ───────────────────────────────────────────────────────

class Tracer:
    """
    Structured tracer for agent workflows.
    Thread-safe. All methods return self for potential chaining.
    """

    def new_trace(
        self,
        workflow: str,
        goal:     str = "",
        **kwargs: Any,
    ) -> str:
        """
        Start a new trace. Returns the trace_id.
        Pass this ID to all subsequent step/error/finish calls.
        """
        trace_id = str(uuid.uuid4())[:8]  # short 8-char ID for readability
        ts       = time.time()

        record = {
            "trace_id":  trace_id,
            "workflow":  workflow,
            "goal":      goal,
            "started_at": ts,
            "started_fmt": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            "status":    "running",
            "steps":     [],
            **kwargs,
        }

        _store.create(trace_id, record)
        _writer.write({**record, "event": "trace_start"})
        _log.info("trace_start", trace_id=trace_id, workflow=workflow, goal=goal[:80])
        return trace_id

    def step(
        self,
        trace_id: str,
        node:     str,
        message:  str = "",
        **kwargs: Any,
    ) -> None:
        """Log a step within a trace."""
        ts = time.time()
        entry = {
            "event":     "step",
            "trace_id":  trace_id,
            "node":      node,
            "message":   message,
            "ts":        ts,
            **kwargs,
        }
        _store.append_step(trace_id, entry)
        _writer.write(entry)

        if cfg.autocode_debug:
            _log.debug("step", trace_id=trace_id, node=node, msg=message[:120])

    def error(
        self,
        trace_id: str,
        node:     str,
        message:  str = "",
        **kwargs: Any,
    ) -> None:
        """Log an error within a trace. Does not stop the trace."""
        ts = time.time()
        entry = {
            "event":    "error",
            "trace_id": trace_id,
            "node":     node,
            "message":  message,
            "ts":       ts,
            **kwargs,
        }
        _store.append_step(trace_id, entry)
        _writer.write(entry)
        _log.warning("error", trace_id=trace_id, node=node, msg=message[:200])

    def finish(
        self,
        trace_id: str,
        success:  bool = True,
        result:   str  = "",
        **kwargs: Any,
    ) -> None:
        """Mark a trace as complete."""
        ts    = time.time()
        trace = _store.get(trace_id)
        elapsed = round(ts - trace["started_at"], 2) if trace else 0.0

        entry = {
            "event":    "trace_finish",
            "trace_id": trace_id,
            "success":  success,
            "result":   result[:200],
            "elapsed_s": elapsed,
            "ts":       ts,
            **kwargs,
        }
        _store.update(trace_id, "status",  "success" if success else "failed")
        _store.update(trace_id, "elapsed", elapsed)
        _store.update(trace_id, "result",  result[:200])
        _store.append_step(trace_id, entry)
        _writer.write(entry)

        icon = "✓" if success else "✗"
        _log.info(
            "trace_finish",
            trace_id=trace_id,
            status="success" if success else "failed",
            elapsed=f"{elapsed}s",
            icon=icon,
        )

    def get(self, trace_id: str) -> Optional[dict]:
        """Retrieve full trace record (for debugging or memory storage)."""
        return _store.get(trace_id)

    def recent(self, n: int = 10) -> list[dict]:
        """Get the N most recent traces, newest first."""
        return _store.all_recent(n)

    def summary(self, trace_id: str) -> str:
        """Return a compact one-line summary of a trace (for memory storage)."""
        trace = _store.get(trace_id)
        if not trace:
            return f"trace {trace_id} not found"

        status  = trace.get("status", "unknown")
        elapsed = trace.get("elapsed", 0)
        steps   = len(trace.get("steps", []))
        goal    = trace.get("goal", "")[:60]

        return (
            f"[{trace_id}] {trace['workflow']} | "
            f"goal={goal!r} | status={status} | "
            f"steps={steps} | elapsed={elapsed}s"
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
tracer = Tracer()