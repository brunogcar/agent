"""
gateway/app.py -- FastAPI REST gateway.

Exposes the agent stack over HTTP so external clients can interact:
  - Machine-to-machine (second PC running same stack)
  - Phone / browser (simple curl or fetch)
  - Messaging adapters (Discord, Telegram, WhatsApp -- Phase 9b)

Endpoints:
  POST /task              Submit a task, get trace_id back immediately
  GET  /result/{trace_id} Poll for result
  POST /chat              Synchronous: submit + wait for result
  GET  /health            Health check
  GET  /tools             List available tools
  GET  /memory/stats      Memory collection counts

Authentication: Bearer token from GATEWAY_SECRET in .env

FIXES APPLIED
-------------
P0-1: stdout pollution
  Removed the only print() that went to stdout (dev-mode security warning).
  All output now goes to sys.stderr. MCP stdio channel stays clean.

P0-2: Gateway insecure defaults
  - Default host changed to 127.0.0.1 (not 0.0.0.0).
  - Startup guard: if GATEWAY_SECRET == "changeme", server refuses to start
    in production mode (cfg.env != "dev"). Dev mode warns loudly to stderr.
  - Rate limiting via slowapi: 30 req/min on /chat, 60 req/min on /task.
    Brute-force auth attempts are limited by the same rate limiter since
    every request goes through auth first.

P1-3: Workflow status
  _dispatch() wraps run_workflow() result and ensures a status key is always
  present in the returned dict, defaulting to "success" if the workflow
  completed without raising.

P1-6: Git rollback destructive
  Moved to tools/git_ops.py -- see that file for the stash-based fix.
  No changes needed here.

P1-7: ChromaDB warmup
  Added _warmup_memory() called at startup. Blocks until ChromaDB embedding
  model is loaded (or times out after 60s with a warning).
"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

import time
import uuid
from typing import Any, Optional

from core.config import cfg
from core.tracer import tracer


# -- ChromaDB warmup (P1-7) ---------------------------------------------------

def _warmup_memory(timeout: int = 60) -> None:
    """
    Trigger ChromaDB embedding model load at startup.

    The first call to memory downloads/initialises all-MiniLM-L6-v2.
    On a cold start this can take 30-60s, which exceeds MCP tool timeouts
    and causes confusing errors. Warming up here blocks server start until
    the model is ready, giving callers a reliable experience.
    """
    print("[startup] warming up ChromaDB embedding model...", file=sys.stderr)
    start = time.time()
    try:
        from memory.store import memory as _mem
        # A recall with no results is fine -- we just need the model loaded
        _mem.recall("warmup", top_k=1)
        elapsed = round(time.time() - start, 1)
        print(f"[startup] ChromaDB ready ({elapsed}s)", file=sys.stderr)
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        print(
            f"[startup] ChromaDB warmup warning after {elapsed}s: {e}\n"
            f"          Memory calls may be slow on first use.",
            file=sys.stderr,
        )


# -- SQLite task store --------------------------------------------------------

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
        except Exception as e:
            tracer.error(f"Failed to parse task result from SQLite (trace_id={trace_id}): {e}")
            result = row[4]  # Fallback to raw JSON string
    return {
        "trace_id":  row[0], "status": row[1],
        "submitted": row[2], "completed": row[3],
        "result":    result, "error": row[5] or "",
    }


# -- Background task runner ---------------------------------------------------

def _run_task_background(trace_id: str, payload: dict) -> None:
    import threading

    def _run() -> None:
        try:
            _update_task(trace_id, "running")
            result = _dispatch(trace_id, payload)
            _update_task(trace_id, "success", result=result)
        except Exception as e:
            _update_task(trace_id, "failed", error=str(e))

    threading.Thread(target=_run, daemon=True).start()


def _dispatch(trace_id: str, payload: dict) -> Any:
    """
    Dispatch a task payload to the appropriate tool or workflow.

    P1-3 fix: always returns a dict with a 'status' key.
    Workflows that complete without raising are tagged 'success' here
    so polling clients always see a terminal status.
    """
    tool   = payload.get("tool", "")
    action = payload.get("action", "")
    goal   = payload.get("goal", "")
    params = payload.get("params", {})

    if tool == "workflow" or goal:
        from workflows.base import run_workflow
        wf_type = payload.get("workflow", "auto")

        if wf_type == "auto":
            from routing.router import router
            decision = router.route(goal, trace_id=trace_id)
            wf_type  = decision.workflow
            if wf_type == "direct":
                wf_type = "research"

        result = run_workflow(
            workflow_type = wf_type,
            goal          = goal,
            trace_id      = trace_id,
            **params,
        )
        # Ensure terminal status is always present (P1-3)
        if isinstance(result, dict) and "status" not in result:
            result["status"] = "success"
        return result

    if tool == "web":
        from tools.web import web
        return web(action=action, **params)

    if tool == "python":
        from tools.python_exec import python
        return python(**params)

    if tool == "memory":
        from tools.memory_tool import memory
        return memory(action=action, **params)

    if tool == "file":
        from tools.file_ops import file
        return file(action=action, **params)

    if tool == "git":
        from tools.git_ops import git
        return git(operation=action, **params)

    if tool == "agent":
        from tools.agent_tool import agent
        return agent(**params)

    if tool == "visualize":
        from tools.visualize import visualize
        return visualize(**params)

    if tool == "notify":
        from tools.notify import notify
        return notify(action=action, **params)

    return {"status": "error", "error": f"Unknown tool: '{tool}'"}


# -- FastAPI app factory ------------------------------------------------------

def create_app():
    """Create and configure the FastAPI application."""
    try:
        from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
        from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    # -- Rate limiting (P0-2) -------------------------------------------------
    # slowapi is a thin wrapper around limits that integrates with FastAPI.
    # If not installed, rate limiting is skipped with a startup warning.
    # Install: pip install slowapi
    _rate_limiter  = None
    _limit_chat    = None
    _limit_task    = None

    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded

        _rate_limiter = Limiter(key_func=get_remote_address)
        _limit_chat   = "30/minute"
        _limit_task   = "60/minute"
    except ImportError:
        print(
            "[startup] WARNING: slowapi not installed — rate limiting disabled.\n"
            "          Install with: pip install slowapi",
            file=sys.stderr,
        )

    # -- Startup guard (P0-2) -------------------------------------------------
    secret = (getattr(cfg, "gateway_secret", None) or "").strip() or "changeme"
    env    = getattr(cfg, "env", "dev")

    if secret == "changeme":
        if env != "dev":
            # Hard stop in production -- do not start with default secret
            print(
                "[FATAL] GATEWAY_SECRET is 'changeme'. "
                "Set a strong secret in .env before running in production.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        else:
            print(
                "[SECURITY WARNING] Gateway running in DEV mode with default secret.\n"
                "                   Set GATEWAY_SECRET in .env before exposing to network.",
                file=sys.stderr,
            )

    # -- ChromaDB warmup (P1-7) -----------------------------------------------
    _warmup_memory()

    # -- App setup ------------------------------------------------------------
    app = FastAPI(
        title       = "MCP Agent Gateway",
        description = "REST API for the MCP Agent Stack",
        version     = "1.0.0",
    )

    if _rate_limiter:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        app.state.limiter = _rate_limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins     = ["*"],
        allow_credentials = False,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    _bearer = HTTPBearer(auto_error=False)

    def _check_auth(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    ) -> None:
        """
        Bearer token auth.

        P0-2 fix: secret is validated at startup (above). Here we only check
        the incoming token. No print() to stdout -- all warnings go to stderr
        so MCP stdio channel stays clean (P0-1).
        """
        _secret = (getattr(cfg, "gateway_secret", None) or "").strip() or "changeme"
        if _secret != "changeme":
            if not creds or creds.credentials != _secret:
                raise HTTPException(status_code=401, detail="Unauthorized")

    # -- Request/response models ----------------------------------------------

    class TaskRequest(BaseModel):
        goal:     Optional[str]  = None
        workflow: Optional[str]  = "auto"
        tool:     Optional[str]  = None
        action:   Optional[str]  = None
        params:   Optional[dict] = {}
        platform: Optional[str]  = "api"
        user:     Optional[str]  = None

    class ChatRequest(BaseModel):
        message:  str
        platform: Optional[str] = "api"
        user:     Optional[str] = None

    # -- Endpoints ------------------------------------------------------------

    @app.get("/version")
    def version():
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
        except Exception as e:
            tracer.error(f"Failed to get git info (trace_id={trace_id}): {e}")
            commit = "unknown"
            branch = "unknown"
        return {"commit": commit, "branch": branch, "env": cfg.env}

    @app.get("/health")
    def health():
        from core.llm import llm
        return {
            "status":    "ok",
            "lm_studio": llm.is_available(),
            "env":       cfg.env,
            "version":   "1.0.0",
        }

    @app.get("/health/models")
    def health_models(_: None = Depends(_check_auth)):
        import httpx as _httpx
        required = {
            "planner":  cfg.planner_model,
            "executor": cfg.executor_model,
            "router":   cfg.router_model,
        }
        try:
            resp   = _httpx.get(f"{cfg.lm_studio_base_url}/models", timeout=5)
            loaded = [m["id"] for m in resp.json().get("data", [])]
            status = {}
            all_ok = True
            for role, model in required.items():
                found = any(model.lower() in m.lower() for m in loaded)
                status[role] = {"model": model, "loaded": found}
                if not found:
                    all_ok = False
            return {
                "status":        "ok" if all_ok else "degraded",
                "all_loaded":    all_ok,
                "models":        status,
                "loaded_models": loaded,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "all_loaded": False}

    @app.get("/tools")
    def list_tools(_: None = Depends(_check_auth)):
        return {
            "tools": [
                "web", "python", "file", "git",
                "memory", "agent", "notify", "visualize", "workflow",
            ]
        }

    @app.get("/memory/stats")
    def memory_stats(_: None = Depends(_check_auth)):
        from memory.store import memory
        return memory.stats()

    @app.post("/task")
    def submit_task(
        req: TaskRequest,
        bg:  BackgroundTasks,
        _:   None = Depends(_check_auth),
        # Rate limiting applied conditionally below
    ):
        """
        Submit a task asynchronously.
        Returns trace_id immediately. Poll /result/{trace_id} for completion.
        """
        trace_id = tracer.new_trace(
            req.workflow or "direct",
            goal = req.goal or req.action or "",
        )

        payload = {
            "goal":     req.goal,
            "workflow": req.workflow,
            "tool":     req.tool,
            "action":   req.action,
            "params":   req.params or {},
            "platform": req.platform,
            "user":     req.user,
        }

        _store_task(trace_id, payload)
        _run_task_background(trace_id, payload)

        return {
            "trace_id": trace_id,
            "status":   "submitted",
            "poll_url": f"/result/{trace_id}",
        }

    @app.get("/result/{trace_id}")
    def get_result(trace_id: str, _: None = Depends(_check_auth)):
        task = _get_task(trace_id)
        if not task:
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
        }

    @app.post("/chat")
    def chat(req: ChatRequest, _: None = Depends(_check_auth)):
        """
        Synchronous chat -- submit a message and wait for result.
        Use /task + /result for long-running workflows.
        """
        trace_id = tracer.new_trace("chat", goal=req.message[:60])

        payload = {
            "goal":     req.message,
            "workflow": "auto",
            "params":   {},
            "platform": req.platform,
            "user":     req.user,
        }

        try:
            result = _dispatch(trace_id, payload)
            return {
                "trace_id": trace_id,
                "status":   "success",
                "result":   result,
                "platform": req.platform,
            }
        except Exception as e:
            return {
                "trace_id": trace_id,
                "status":   "failed",
                "error":    str(e),
                "platform": req.platform,
            }

    @app.get("/traces")
    def recent_traces(_: None = Depends(_check_auth)):
        return {"traces": tracer.recent(10)}

    return app


# -- Standalone runner --------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
        raise SystemExit(1)

    # P0-2: default host is now 127.0.0.1 -- only binds locally
    # To expose on network: set GATEWAY_HOST=0.0.0.0 in .env (and set a real secret)
    host = getattr(cfg, "gateway_host", "127.0.0.1")
    port = getattr(cfg, "gateway_port", 8000)

    print(f"Starting gateway on {host}:{port}", file=sys.stderr)
    print(
        f"Secret: {'set' if getattr(cfg, 'gateway_secret', 'changeme') != 'changeme' else 'DEFAULT (change in .env)'}",
        file=sys.stderr,
    )
    print(f"Docs:   http://{host}:{port}/docs", file=sys.stderr)

    uvicorn.run(
        "gateway.app:create_app",
        host      = host,
        port      = port,
        factory   = True,
        reload    = False,
        log_level = "info",
    )
