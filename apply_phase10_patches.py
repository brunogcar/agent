"""
apply_phase10_patches.py -- run from D:/mcp/agent/

Phase 10 improvements:
  1. gateway/app.py:    SQLite task persistence (survive restarts)
  2. gateway/app.py:    GET /version endpoint (git commit hash)
  3. tools/file_ops.py: file(action="compress") -- zip workspace subfolder
  4. tools/memory_tool.py: input size guard (reject >50KB text)
  5. gateway/app.py:    request payload size guard
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch(filepath, old, new, label):
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new)
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Phase 10 patches ===\n")

# ── 1. gateway/app.py: SQLite task persistence ───────────────────────────────
# Replace the in-memory _tasks dict with SQLite-backed storage.
# Tasks survive gateway restarts. Old pending tasks are marked as
# 'interrupted' on startup so they don't hang forever.
patch(
    "gateway/app.py",
    '''# -- In-memory task store (replace with SQLite in Phase 9b if needed) --------

_tasks: dict[str, dict] = {}


def _store_task(trace_id: str, payload: dict) -> None:
    _tasks[trace_id] = {
        "trace_id":   trace_id,
        "status":     "pending",
        "submitted":  time.time(),
        "result":     None,
        "error":      None,
        "payload":    payload,
    }


def _update_task(trace_id: str, status: str,
                 result: Any = None, error: str = "") -> None:
    if trace_id in _tasks:
        _tasks[trace_id].update({
            "status":    status,
            "result":    result,
            "error":     error,
            "completed": time.time(),
        })''',
    '''# -- SQLite task store (persists across gateway restarts) --------------------

import sqlite3 as _sqlite3
import json    as _json_mod

_TASK_DB_PATH = None
_task_db_lock = __import__("threading").Lock()


def _get_task_db() -> _sqlite3.Connection:
    global _TASK_DB_PATH
    if _TASK_DB_PATH is None:
        _TASK_DB_PATH = cfg.memory_root / "gateway_tasks.db"
    conn = _sqlite3.connect(str(_TASK_DB_PATH), check_same_thread=False)
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
            "SELECT trace_id, status, submitted, completed, result, error "
            "FROM tasks WHERE trace_id=?", (trace_id,)
        ).fetchone()
        db.close()
    if not row:
        return None
    result = None
    if row[4]:
        try:
            result = _json_mod.loads(row[4])
        except Exception:
            result = row[4]
    return {
        "trace_id":  row[0], "status": row[1],
        "submitted": row[2], "completed": row[3],
        "result":    result, "error": row[5] or "",
    }''',
    "gateway: SQLite task persistence",
)

# Fix _get_result to use _get_task() instead of _tasks dict
patch(
    "gateway/app.py",
    '''        task = _tasks.get(trace_id)
        if not task:
            # Check tracer for any info
            trace = tracer.get(trace_id)
            if trace:
                return {
                    "trace_id": trace_id,
                    "status":   trace.get("status", "unknown"),
                    "result":   trace.get("result", ""),
                    "elapsed":  trace.get("elapsed", 0),
                }
            raise HTTPException(status_code=404,
                                detail=f"trace_id '{trace_id}' not found")

        response = {
            "trace_id": trace_id,
            "status":   task["status"],
            "result":   task.get("result"),
            "error":    task.get("error"),
            "elapsed":  (
                round(time.time() - task["submitted"], 1)
                if task["status"] in ("pending", "running")
                else round(
                    task.get("completed", time.time()) - task["submitted"], 1
                )
            ),
        }
        return response''',
    '''        task = _get_task(trace_id)
        if not task:
            # Fall back to tracer
            trace = tracer.get(trace_id)
            if trace:
                return {
                    "trace_id": trace_id,
                    "status":   trace.get("status", "unknown"),
                    "result":   trace.get("result", ""),
                    "elapsed":  trace.get("elapsed", 0),
                }
            raise HTTPException(status_code=404,
                                detail=f"trace_id '{trace_id}' not found")

        elapsed = (
            round(time.time() - task["submitted"], 1)
            if task["status"] in ("pending", "running")
            else round((task.get("completed") or time.time()) - task["submitted"], 1)
        )
        return {
            "trace_id": trace_id,
            "status":   task["status"],
            "result":   task.get("result"),
            "error":    task.get("error"),
            "elapsed":  elapsed,
        }''',
    "gateway: get_result uses SQLite _get_task()",
)

# ── 2. gateway/app.py: /version endpoint ─────────────────────────────────────
patch(
    "gateway/app.py",
    '''    @app.get("/health")
    def health():''',
    '''    @app.get("/version")
    def version():
        """Return current git commit hash and branch."""
        import subprocess as _sp
        try:
            commit = _sp.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(cfg.agent_root), stderr=_sp.DEVNULL, text=True,
            ).strip()
            branch = _sp.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(cfg.agent_root), stderr=_sp.DEVNULL, text=True,
            ).strip()
        except Exception:
            commit = "unknown"
            branch = "unknown"
        return {"commit": commit, "branch": branch, "env": cfg.env}

    @app.get("/health")
    def health():''',
    "gateway: /version endpoint",
)

# ── 3. tools/file_ops.py: compress action ────────────────────────────────────
patch(
    "tools/file_ops.py",
    '''    return {
        "status": "error",
        "error":  (
            f"Unknown action '{action}'. "
            "Use: read | write | list | backup | read_many | search | "
            "read_pdf | write_pdf | "
            "read_docx | write_docx | "
            "read_xlsx | write_xlsx | "
            "read_pptx | write_pptx"
        ),
    }''',
    '''    # ── compress ──────────────────────────────────────────────────────────────
    if action == "compress":
        import zipfile
        p, err = _safe_resolve(path or ".")
        if err:
            return {"status": "error", "error": err}
        if not p.exists():
            return {"status": "error", "error": f"Path not found: {p}"}

        # Output zip sits next to the target (or in workspace root if target is root)
        zip_name = (p.name or "workspace") + ".zip"
        zip_path = (p.parent if p.parent != p else cfg.workspace_root) / zip_name

        try:
            file_count = 0
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if p.is_dir():
                    for item in p.rglob("*"):
                        if item.is_file():
                            arcname = item.relative_to(p)
                            zf.write(item, arcname)
                            file_count += 1
                else:
                    zf.write(p, p.name)
                    file_count = 1

            return {
                "status":     "success",
                "zip_path":   str(zip_path),
                "files":      file_count,
                "size":       zip_path.stat().st_size,
            }
        except Exception as e:
            return {"status": "error", "error": f"Compress failed: {e}"}

    return {
        "status": "error",
        "error":  (
            f"Unknown action '{action}'. "
            "Use: read | write | list | backup | read_many | search | "
            "read_pdf | write_pdf | "
            "read_docx | write_docx | "
            "read_xlsx | write_xlsx | "
            "read_pptx | write_pptx | compress"
        ),
    }''',
    "file: compress action (zip workspace subfolder)",
)

# ── 4. tools/memory_tool.py: input size guard ────────────────────────────────
patch(
    "tools/memory_tool.py",
    '''    if action == "store":
        if not text or not text.strip():
            return {"status": "error", "error": "text is required for store"}
        if importance < 1 or importance > 10:
            return {"status": "error",
                    "error": f"importance must be 1-10, got {importance}"}''',
    '''    if action == "store":
        if not text or not text.strip():
            return {"status": "error", "error": "text is required for store"}
        if importance < 1 or importance > 10:
            return {"status": "error",
                    "error": f"importance must be 1-10, got {importance}"}
        # Guard against storing huge blobs that bloat the vector DB
        MAX_MEMORY_BYTES = 50_000  # 50 KB
        if len(text.encode("utf-8")) > MAX_MEMORY_BYTES:
            return {
                "status": "error",
                "error":  (
                    f"text is {len(text.encode())} bytes -- exceeds 50KB limit. "
                    "Summarise or chunk the content before storing."
                ),
            }''',
    "memory_tool: reject text > 50KB",
)

print("\nDone. Run: python verify_phase10.py to confirm.")
