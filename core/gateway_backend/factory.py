"""
core/gateway_backend/factory.py — FastAPI app factory and composition root.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import cfg
from core.tracer import tracer
from contextlib import asynccontextmanager
import threading

# Import routers
from core.gateway_backend.routes import tasks, chat, health, metrics, traces

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern FastAPI lifespan context manager.
    Handles startup (warmup, executor init) and shutdown (executor drain).
    """
    # ── STARTUP ─────────────────────────────────────────────────────────────
    
    # 1. ChromaDB warmup (Run in daemon thread to avoid blocking the async event loop)
    warmup_thread = threading.Thread(target=_warmup_memory, daemon=True)
    warmup_thread.start()
    
    # 2. Initialize ThreadPoolExecutor
    from core.runtime.task_runner import init_executor
    init_executor()
    
    yield  # ── APP RUNS HERE ──
    
    # ── SHUTDOWN ────────────────────────────────────────────────────────────
    
    # 1. Drain and shutdown ThreadPoolExecutor
    from core.runtime.task_runner import shutdown_executor
    shutdown_executor()
    
    # 2. Wait for warmup thread to finish (if it hasn't already)
    warmup_thread.join(timeout=5)

# ── ChromaDB warmup (P1-7) ---------------------------------------------------
def _warmup_memory(timeout: int = 60) -> None:
    """
    Trigger ChromaDB embedding model load at startup.
    The first call to memory downloads/initialises all-MiniLM-L6-v2.
    On a cold start this can take 30-60s, which exceeds MCP tool timeouts
    and causes confusing errors. Warming up here blocks server start until
    the model is ready, giving callers a reliable experience.
    """
    def _do_warmup() -> None:
        """Inner function to run warmup in isolated thread."""
        from core.memory import memory as _mem
        # A recall with no results is fine -- we just need the model loaded
        _mem.recall("warmup", top_k=1)

    print("[startup] warming up ChromaDB embedding model...", file=sys.stderr)
    start = time.time()
    try:
        # Run warmup in thread with hard timeout to prevent indefinite hangs
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_warmup)
            future.result(timeout=timeout)

        elapsed = round(time.time() - start, 1)
        print(f"[startup] ChromaDB ready ({elapsed}s)", file=sys.stderr)

    except FuturesTimeoutError:
        elapsed = round(time.time() - start, 1)
        print(
            f"[startup] ChromaDB warmup TIMEOUT after {elapsed}s — proceeding in degraded mode\n"
            f"          Memory calls may be slow on first use.",
            file=sys.stderr,
        )
        # Log to tracer so it shows up in structured debugging/telemetry
        tracer.warning("memory_warmup_timeout", timeout=timeout, elapsed=elapsed, msg="Proceeding in degraded mode")
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        print(
            f"[startup] ChromaDB warmup warning after {elapsed}s: {e}\n"
            f"          Memory calls may be slow on first use.",
            file=sys.stderr,
        )

def create_app():
    """Create and configure the FastAPI application."""
    # ── Rate limiting (P0-2) -------------------------------------------------
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

    # ── Startup guard (P0-2) -------------------------------------------------
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

    # [PHASE 2 FIX] Config validation on startup (Runs synchronously before app creation)
    from core.config_validation import validate_config
    validate_config()

    # ── App setup ------------------------------------------------------------
    # Note: ChromaDB warmup and Executor init are now handled in the lifespan context
    app = FastAPI(
        title        = "MCP Agent Gateway",
        description  = "REST API for the MCP Agent Stack",
        version      = "1.0.0",
        lifespan     = lifespan,  # 🔴 PHASE 2: Wire modern lifespan context
    )

    if _rate_limiter:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        app.state.limiter = _rate_limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS Configuration (Audit Fix #1) ------------------------------------
    # Read from config to prevent wildcard exposure in production.
    # In .env, set GATEWAY_CORS_ORIGINS="http://localhost:3000,https://mydomain.com"
    cors_origins = getattr(cfg, "gateway_cors_origins", ["*"])
    if isinstance(cors_origins, str):
        cors_origins = [o.strip() for o in cors_origins.split(",")]
        
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = cors_origins,
        allow_credentials = False,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # ── Payload Size Limit (Audit Fix #2) ------------------------------------
    # Prevents OOM crashes from multi-gigabyte malicious payloads.
    # Defaults to 10MB. Override in .env with GATEWAY_MAX_BODY_MB=50
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    
    MAX_BODY_SIZE = getattr(cfg, "gateway_max_body_mb", 10) * 1024 * 1024
    
    class MaxBodySizeMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, max_body_size: int):
            super().__init__(app)
            self.max_body_size = max_body_size

        async def dispatch(self, request, call_next):
            if request.method in ("POST", "PUT", "PATCH"):
                content_length = request.headers.get("content-length")
                if content_length and int(content_length) > self.max_body_size:
                    return JSONResponse(
                        status_code=413, 
                        content={"error": "Payload too large", "max_mb": self.max_body_size // (1024*1024)}
                    )
            return await call_next(request)

    app.add_middleware(MaxBodySizeMiddleware, max_body_size=MAX_BODY_SIZE)

    # ── Request-ID Middleware (Phase 2 Step 1.5) --------------------------
    # Guarantees every request has a trace_id available for exception handlers
    # and logging. Echoes it back in the X-Request-ID response header.
    import uuid
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    
    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Read from header or generate new UUID
            request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            request.state.trace_id = request_id
            
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    app.add_middleware(RequestIDMiddleware)

    # ── Register Routers (Phase 2 Step 4: OpenAPI Tags) ----------------------
    app.include_router(tasks.router,   tags=["Tasks"])
    app.include_router(chat.router,    tags=["Chat"])
    app.include_router(health.router,  tags=["Health & System"])
    app.include_router(metrics.router, tags=["Telemetry"])
    app.include_router(traces.router,  tags=["Traces"])

    # ── Centralized Exception Handlers (Phase 2 Step 2) ----------------------
    from core.gateway_backend.exceptions import TaskNotFoundError, ToolExecutionError
    from fastapi.responses import JSONResponse
    from fastapi import Request

    @app.exception_handler(TaskNotFoundError)
    async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
        trace_id = getattr(request.state, "trace_id", exc.trace_id)
        tracer.error(event="task_not_found", node="gateway", trace_id=trace_id, error=str(exc))
        return JSONResponse(
            status_code=404,
            content={"error": "Task not found", "trace_id": trace_id, "detail": str(exc)}
        )

    @app.exception_handler(ToolExecutionError)
    async def tool_execution_handler(request: Request, exc: ToolExecutionError):
        trace_id = getattr(request.state, "trace_id", exc.trace_id)
        tracer.error(event="tool_execution_failed", node="gateway", trace_id=trace_id, tool=exc.tool, error=exc.error)
        return JSONResponse(
            status_code=500,
            content={"error": "Tool execution failed", "trace_id": trace_id, "tool": exc.tool, "detail": exc.error}
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", "unknown")
        tracer.error(event="unhandled_exception", node="gateway", trace_id=trace_id, error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "trace_id": trace_id}
        )

    return app