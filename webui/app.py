"""webui/app.py — FastAPI app factory for the WebUI.

[WebUI v1] Creates the FastAPI app. Mounts:
  - /webui/*         → HTML pages (server-rendered Jinja2)
  - /api/webui/*     → JSON data + HTMX partials
  - /api/webui/sync/* → sync status + SSE stream
  - /static/*        → CSS, JS, vendor (HTMX, Alpine, Chart.js)

Also mounts the existing gateway routes (/chat, /task, /ws, /health, etc.)
on the same app — one process, one port. LM Studio / Claude Desktop
continue to use server.py (MCP stdio) separately.
"""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import threading


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: startup freshness check (non-blocking) + shutdown."""
    # ── Startup ─────────────────────────────────────────────────────────────
    print("[webui] Startup: freshness check", file=sys.stderr)
    # Non-blocking freshness check in a daemon thread
    def _check():
        try:
            from webui.services.sync import SyncService
            svc = SyncService()
            fresh = svc.freshness()
            stale = [k for k, v in fresh.items() if v.get("stale")]
            if stale:
                print(f"[webui] {len(stale)} stale sources: {', '.join(stale)}", file=sys.stderr)
            else:
                print("[webui] All sources fresh", file=sys.stderr)
        except Exception as e:
            print(f"[webui] Freshness check failed: {e}", file=sys.stderr)
    threading.Thread(target=_check, daemon=True).start()

    yield

    # ── Shutdown ────────────────────────────────────────────────────────────
    print("[webui] Shutdown", file=sys.stderr)


def create_app() -> FastAPI:
    """Create and configure the WebUI FastAPI app."""
    app = FastAPI(
        title="Brazilian Financial Data WebUI",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS (allow localhost dev) ──────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000",
                       "http://127.0.0.1:3000", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static files (CSS, JS, vendor) ──────────────────────────────────────
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ── WebUI routes ─────────────────────────────────────────────────────────
    from webui.routes import pages, api, sync
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(sync.router)

    # ── Existing gateway routes (optional — mount if available) ─────────────
    # This brings /chat, /task, /ws, /health onto the same app so the WebUI
    # can also drive the agent. Wrapped in try/except so the WebUI still
    # works if the gateway has import issues.
    try:
        from core.gateway_backend.routes import tasks, chat, health, metrics, traces, reports, websocket
        app.include_router(tasks.router, tags=["Tasks"])
        app.include_router(chat.router, tags=["Chat"])
        app.include_router(health.router, tags=["Health"])
        app.include_router(metrics.router, tags=["Metrics"])
        app.include_router(traces.router, tags=["Traces"])
        app.include_router(reports.router, tags=["Reports"])
        app.include_router(websocket.router, tags=["WebSocket"])
        print("[webui] Gateway routes mounted (/chat, /task, /ws, /health)", file=sys.stderr)
    except Exception as e:
        print(f"[webui] Gateway routes NOT mounted: {e}", file=sys.stderr)

    # ── Root redirect to /webui ─────────────────────────────────────────────
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/webui", status_code=302)

    return app
