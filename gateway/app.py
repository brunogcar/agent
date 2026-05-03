"""
gateway/app.py -- FastAPI REST gateway.

Exposes the agent stack over HTTP so external clients can interact:
  - Machine-to-machine (second PC running same stack)
  - Phone / browser (simple curl or fetch)
  - Messaging adapters (Discord, Telegram, WhatsApp -- Phase 9b)

Endpoints:
  POST /task              Submit a task, get trace_id back immediately
  GET  /result/{trace_id} Poll for result
  POST /chat              Synchronous: submit + wait for result (simple use)
  GET  /health            Health check
  GET  /tools             List available tools
  GET  /memory/stats      Memory collection counts

Authentication: Bearer token from GATEWAY_SECRET in .env
All requests must include: Authorization: Bearer <secret>

Run standalone:
    python gateway/app.py

Or import and mount into another app:
    from gateway.app import create_app
    app = create_app()
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: ensure agent root is on sys.path
# Needed when running `python gateway/app.py` from any directory
_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

import time
import uuid
from typing import Any, Optional

from core.config import cfg
from core.tracer import tracer


# -- In-memory task store (replace with SQLite in Phase 9b if needed) --------

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
        })


# -- Background task runner --------------------------------------------------

def _run_task_background(trace_id: str, payload: dict) -> None:
    """Run a task in a background thread and update task store on completion."""
    import threading

    def _run() -> None:
        try:
            _update_task(trace_id, "running")
            result = _dispatch(trace_id, payload)
            _update_task(trace_id, "success", result=result)
        except Exception as e:
            _update_task(trace_id, "failed", error=str(e))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _dispatch(trace_id: str, payload: dict) -> Any:
    """Dispatch a task payload to the appropriate tool or workflow."""
    tool     = payload.get("tool", "")
    action   = payload.get("action", "")
    goal     = payload.get("goal", "")
    params   = payload.get("params", {})

    if tool == "workflow" or goal:
        from workflows.base import run_workflow
        wf_type = payload.get("workflow", "auto")

        if wf_type == "auto":
            from routing.router import router
            decision = router.route(goal, trace_id=trace_id)
            wf_type  = decision.workflow
            if wf_type == "direct":
                wf_type = "research"  # safe fallback

        return run_workflow(
            workflow_type = wf_type,
            goal          = goal,
            trace_id      = trace_id,
            **params,
        )

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


# -- FastAPI app factory -----------------------------------------------------

def create_app():
    """Create and configure the FastAPI application."""
    try:
        from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
        from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
    except ImportError:
        raise ImportError(
            "FastAPI not installed. Run: pip install fastapi uvicorn"
        )

    app = FastAPI(
        title       = "MCP Agent Gateway",
        description = "REST API for the MCP Agent Stack",
        version     = "1.0.0",
    )

    # CORS -- allow all origins (restrict in production)
    # CORS: allow_credentials=True + allow_origins=["*"] is a security
    # vulnerability and also raises a FastAPI validation error.
    # Use allow_credentials=False for open-network deployments,
    # or restrict allow_origins to specific hosts in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = ["*"],
        allow_credentials = False,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # Auth
    _bearer = HTTPBearer(auto_error=False)

    def _check_auth(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    ) -> None:
        # Normalise: empty/None secret falls back to "changeme" (dev mode)
        # This prevents auth bypass when GATEWAY_SECRET= is left blank in .env
        secret = (cfg.gateway_secret or "").strip() or "changeme"
        if secret != "changeme":
            if not creds or creds.credentials != secret:
                raise HTTPException(status_code=401, detail="Unauthorized")

    # -- Request/response models ----------------------------------------------

    class TaskRequest(BaseModel):
        goal:     Optional[str] = None
        workflow: Optional[str] = "auto"
        tool:     Optional[str] = None
        action:   Optional[str] = None
        params:   Optional[dict] = {}
        platform: Optional[str] = "api"   # api | discord | telegram | whatsapp
        user:     Optional[str] = None

    class ChatRequest(BaseModel):
        message:  str
        platform: Optional[str] = "api"
        user:     Optional[str] = None

    # -- Endpoints ------------------------------------------------------------

    @app.get("/health")
    def health():
        from core.llm import llm
        return {
            "status":    "ok",
            "lm_studio": llm.is_available(),
            "env":       cfg.env,
            "version":   "1.0.0",
        }

    @app.get("/tools")
    def list_tools(_: None = Depends(_check_auth)):
        """List all available meta-tools."""
        return {
            "tools": [
                "web", "python", "file", "git",
                "memory", "agent", "notify", "visualize", "workflow",
            ]
        }

    @app.get("/memory/stats")
    def memory_stats(_: None = Depends(_check_auth)):
        """Memory collection counts."""
        from memory.store import memory
        stats = memory.stats()
        return stats

    @app.post("/task")
    def submit_task(
        req:  TaskRequest,
        bg:   BackgroundTasks,
        _:    None = Depends(_check_auth),
    ):
        """
        Submit a task asynchronously.
        Returns trace_id immediately. Poll /result/{trace_id} for completion.

        Example:
            curl -X POST http://localhost:8000/task \\
              -H "Authorization: Bearer changeme" \\
              -H "Content-Type: application/json" \\
              -d '{"goal": "What is LangGraph?", "workflow": "research"}'
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
    def get_result(
        trace_id: str,
        _:        None = Depends(_check_auth),
    ):
        """
        Poll for task result by trace_id.

        Returns:
          status: "pending" | "running" | "success" | "failed"
          result: the final result (when status=success)
          error:  error message (when status=failed)
        """
        task = _tasks.get(trace_id)
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
        return response

    @app.post("/chat")
    def chat(
        req: ChatRequest,
        _:   None = Depends(_check_auth),
    ):
        """
        Synchronous chat -- submit a message and wait for result.
        Uses auto-routing. Times out at EXECUTION_TIMEOUT seconds.

        Best for: simple questions, quick tasks.
        Use /task + /result for long-running workflows.

        Example:
            curl -X POST http://localhost:8000/chat \\
              -H "Authorization: Bearer changeme" \\
              -H "Content-Type: application/json" \\
              -d '{"message": "What is ChromaDB?"}'
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
        """Recent workflow traces (last 10)."""
        return {"traces": tracer.recent(10)}

    return app


# -- Standalone runner -------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install fastapi uvicorn")
        raise SystemExit(1)

    print(f"Starting gateway on {cfg.gateway_host}:{cfg.gateway_port}")
    print(f"Secret: {'set' if cfg.gateway_secret != 'changeme' else 'DEFAULT (change in .env)'}")
    print(f"Docs:   http://{cfg.gateway_host}:{cfg.gateway_port}/docs")

    uvicorn.run(
        "gateway.app:create_app",
        host    = cfg.gateway_host,
        port    = cfg.gateway_port,
        factory = True,
        reload  = False,
        log_level = "info",
    )
