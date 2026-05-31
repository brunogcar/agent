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

# Import routers
from core.gateway_backend.routes import tasks, chat, health, metrics, traces

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

    # ── ChromaDB warmup (P1-7) -----------------------------------------------
    _warmup_memory()

    # [PHASE 2 FIX] Config validation on startup
    from core.config_validation import validate_config
    validate_config()

    # ── App setup ------------------------------------------------------------
    app = FastAPI(
        title        = "MCP Agent Gateway",
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

    # ── Register Routers -----------------------------------------------------
    app.include_router(tasks.router)
    app.include_router(chat.router)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(traces.router)

    return app