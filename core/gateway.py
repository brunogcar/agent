"""
core/gateway.py -- FastAPI REST gateway.

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
  Default host changed to 127.0.0.1 (not 0.0.0.0).
  Startup guard: if GATEWAY_SECRET == "changeme", server refuses to start
  in production mode (cfg.env != "dev"). Dev mode warns loudly to stderr.
  Rate limiting via slowapi: 30 req/min on /chat, 60 req/min on /task.
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
import threading
from typing import Any, Optional

from core.config import cfg
from core.tracer import tracer
from core.gateway_backend.models import TaskRequest, ChatRequest
from core.gateway_backend.dependencies import check_auth
from core.gateway_backend.store import _store_task, _update_task, _get_task
from core.gateway_backend.dispatcher import dispatch as _dispatch
from core.runtime.task_runner import run_background_task
from core.gateway_backend.factory import create_app

# ── FastAPI & Pydantic imports (Module-level for ForwardRef resolution) ────
# Must be at module level because `from __future__ import annotations` turns
# type hints into strings. FastAPI needs these in the global namespace to
# resolve them correctly when registering routes inside the factory.
try:
    from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, Query
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    raise ImportError("FastAPI/Pydantic not installed. Run: pip install fastapi uvicorn pydantic")


# ── Thin Facade & Standalone runner ------------------------------------------
app = create_app()

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
        "core.gateway:create_app",  # [FIX] Corrected factory path
        host      = host,
        port      = port,
        factory   = True,
        reload    = False,
        log_level = "info",
    )