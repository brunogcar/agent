# core/gateway_backend/store.py — SQLite task store for async HTTP task checkpointing.
"""Thread-safe persistence for the async task journal."""
from __future__ import annotations

import sqlite3 as _sqlite3
import json as _json_mod
import time
import threading
import sys
from typing import Any

from core.config import cfg
from core.tracer import tracer

_TASK_DB_PATH = None
_task_db_lock = threading.Lock()

_task_db_conn: _sqlite3.Connection | None = None

def _get_task_db() -> _sqlite3.Connection:
    """v1.1: Return the singleton SQLite connection (was: per-call open/close).

    The connection is created once and reused across all calls. Thread-safe
    via _task_db_lock (callers already hold it). WAL mode + busy_timeout
    prevent lock contention. The connection is never closed during the
    process lifetime (SQLite handles cleanup on process exit).
    """
    global _TASK_DB_PATH, _task_db_conn
    if _task_db_conn is not None:
        return _task_db_conn

    try:
        if _TASK_DB_PATH is None:
            _TASK_DB_PATH = cfg.memory_root / "gateway_tasks.db"
        _task_db_conn = _sqlite3.connect(str(_TASK_DB_PATH), check_same_thread=False, timeout=30.0)
        _task_db_conn.execute("PRAGMA journal_mode=WAL;")
        _task_db_conn.execute("PRAGMA busy_timeout=5000;")
        _task_db_conn.execute("PRAGMA wal_autocheckpoint=1000;")
        _task_db_conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                trace_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                submitted REAL NOT NULL,
                completed REAL,
                result TEXT,
                error TEXT,
                payload TEXT
            )
        """)
        _task_db_conn.commit()
        return _task_db_conn
    except Exception as e:
        tracer.error("", "store_init", f"SQLite init failed: {e}")
        error_str = str(e).lower()
        if any(kw in error_str for kw in ['permission denied', 'no such file or directory', 'read-only']):
            print(f"\n[FATAL] SQLite database initialization failed: {e}", file=sys.stderr)
            raise
        return _sqlite3.connect(str(_TASK_DB_PATH))

def _store_task(trace_id: str, payload: dict) -> None:
    with _task_db_lock:
        db = _get_task_db()
        db.execute(
            "INSERT OR REPLACE INTO tasks (trace_id, status, submitted, payload) "
            "VALUES (?, 'pending', ?, ?)",
            (trace_id, time.time(), _json_mod.dumps(payload)),
        )
        db.commit()  # v1.1: singleton — no close

def _update_task(trace_id: str, status: str,
                 result: Any = None, error: str = "") -> None:
    with _task_db_lock:
        db = _get_task_db()
        db.execute(
            "UPDATE tasks SET status=?, completed=?, result=?, error=? "
            "WHERE trace_id=?",
            (status, time.time(),
             _json_mod.dumps(result) if result is not None else None,
             error, trace_id),
        )
        db.commit()  # v1.1: singleton — no close

def _get_task(trace_id: str) -> dict | None:
    with _task_db_lock:
        db = _get_task_db()
        row = db.execute(
            "SELECT trace_id, status, submitted, completed, result, error"
            " FROM tasks WHERE trace_id=?", (trace_id,)
        ).fetchone()
        # v1.1: singleton — no close
        if not row:
            return None

        result = None
        if row[4]:
            try:
                result = _json_mod.loads(row[4])
            except Exception as e:
                tracer.error(trace_id, "store_parse", f"Failed to parse task result: {e}")
                result = row[4] # Fallback to raw JSON string

        return {
            "trace_id": row[0], "status": row[1],
            "submitted": row[2], "completed": row[3],
            "result": result, "error": row[5] or "",
        }
