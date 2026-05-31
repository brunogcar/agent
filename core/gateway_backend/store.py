"""
core/gateway_backend/store.py — SQLite task store for async HTTP task checkpointing.

EXTRACTION NOTE (Gateway Phase 1): Extracted from core/gateway.py.
Provides thread-safe persistence for the async task journal.
"""
from __future__ import annotations

import sqlite3 as _sqlite3
import json    as _json_mod
import time
import threading
import sys
from typing import Any

from core.config import cfg
from core.tracer import tracer

_TASK_DB_PATH = None
_task_db_lock = threading.Lock()

def _get_task_db() -> _sqlite3.Connection:
    global _TASK_DB_PATH
    try:
        if _TASK_DB_PATH is None:
            _TASK_DB_PATH = cfg.memory_root / "gateway_tasks.db"
        conn = _sqlite3.connect(str(_TASK_DB_PATH), check_same_thread=False, timeout=30.0)
        # Strategy C: Enable WAL mode and busy_timeout to prevent lock contention
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA wal_autocheckpoint=1000;")  # Prevents unbounded .wal growth
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                trace_id  TEXT PRIMARY KEY,
                status    TEXT NOT NULL DEFAULT 'pending',
                submitted REAL NOT NULL,
                completed REAL,
                result    TEXT,
                error     TEXT, 
                payload   TEXT
            )
        """)
        conn.commit()
        return conn
    except Exception as e:
        tracer.error(f"Failed to initialize SQLite task database at {_TASK_DB_PATH}: {e}")
        # Check for critical errors that should prevent startup
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
        db.commit()
        db.close()

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
        db.commit()
        db.close()

def _get_task(trace_id: str) -> dict | None:
    with _task_db_lock:
        db  = _get_task_db()
        row = db.execute(
            "SELECT trace_id, status, submitted, completed, result, error"
            " FROM tasks WHERE trace_id=?", (trace_id,)
        ).fetchone()
        db.close()
    if not row:
        return None

    result = None
    if row[4]:
        try:
            result = _json_mod.loads(row[4])
        except Exception as e:
            tracer.error(f"Failed to parse task result from SQLite (trace_id={trace_id}): {e}")
            result = row[4]  # Fallback to raw JSON string

    return {
        "trace_id":  row[0],   "status": row[1],
        "submitted": row[2],   "completed": row[3],
        "result":    result,    "error": row[5] or "",
    }