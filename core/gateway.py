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
    
EXTRACTION NOTE (Gateway Phase 1):
    This file is now a Thin Facade. All implementation logic (routes, store,
    dispatcher, models, dependencies, warmup) has been extracted into:
    - core/gateway_backend/ (HTTP engine)
    - core/runtime/task_runner.py (Process governance)
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Import Path Fix ─────────────────────────────────────────────────────────
_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# ── Thin Facade ─────────────────────────────────────────────────────────────
from core.gateway_backend.factory import create_app

app = create_app()

# ── Standalone runner ───────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
        raise SystemExit(1)
        
    from core.config import cfg
    
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