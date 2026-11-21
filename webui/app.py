"""webui/app.py — FastAPI app factory for the WebUI.

[WebUI v1] Creates the FastAPI app. Mounts:
  - /webui/*         → HTML pages (server-rendered Jinja2)
  - /api/webui/*     → JSON data + HTMX partials
  - /api/webui/sync/* → sync status + SSE stream
  - /static/*        → CSS, JS, vendor (HTMX, Alpine, Chart.js)

Also mounts the existing gateway routes (/chat, /task, /ws, /health, etc.)
on the same app — one process, one port. LM Studio / Claude Desktop
continue to use server.py (MCP stdio) separately.

[WebUI v1.5] HARDENING:
  - TrustedHostMiddleware: loopback-only by default (127.0.0.1, localhost,
    ::1). The gateway routers (/task, /chat, /ws) execute agent tools
    unauthenticated — binding --host 0.0.0.0 used to expose them to the
    whole LAN. Non-loopback binds now require WEBUI_ALLOW_LAN=1. This
    keeps the "no auth" constraint while closing the accidental-LAN hole.
  - CORS: origin regex covers any localhost port (was hardcoded to
    :8000/:3000 — a custom --port silently broke the allow-list).
  - --no-sync is honored via the WEBUI_NO_SYNC env var (set by webui.py;
    survives uvicorn's factory + --reload subprocess boundaries).
  - The lifespan uses the routes' SyncService singleton (was a 3rd
    instance) and its freshness check is skipped when --no-sync is set.
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles


def _allow_lan() -> bool:
    return os.environ.get("WEBUI_ALLOW_LAN", "") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: startup freshness check (non-blocking, skippable) + shutdown.

    This is a freshness CHECK (logs stale sources) — it never syncs.
    WEBUI_NO_SYNC=1 (set by `python webui.py --no-sync`) skips it.
    """
    if os.environ.get("WEBUI_NO_SYNC", "") == "1":
        print("[webui] Startup freshness check skipped (--no-sync)", file=sys.stderr)
    else:
        print("[webui] Startup: freshness check", file=sys.stderr)

        def _check():
            try:
                # Reuse the sync router's service instance (the app used to
                # create a 3rd SyncService here — routes had two more).
                from webui.routes.sync import _sync_service
                fresh = _sync_service.freshness()
                stale = [k for k, v in fresh.items() if v.get("stale")]
                if stale:
                    print(f"[webui] {len(stale)} stale sources: {', '.join(stale)}",
                          file=sys.stderr)
                else:
                    print("[webui] All sources fresh", file=sys.stderr)
            except Exception as e:
                print(f"[webui] Freshness check failed: {e}", file=sys.stderr)

        threading.Thread(target=_check, daemon=True).start()

    yield

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

    # ── Trusted hosts: loopback-only unless WEBUI_ALLOW_LAN=1 ───────────────
    # The mounted gateway routes (/task, /chat, /ws) run agent tools with no
    # auth; DNS-rebinding and accidental `--host 0.0.0.0` are closed off.
    # "0.0.0.0" is kept as a Host value (browsing http://0.0.0.0:PORT works).
    if _allow_lan():
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
    else:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["127.0.0.1", "localhost", "0.0.0.0", "::1"],
        )

    # ── CORS (any localhost port — the old hardcoded :8000/:3000 list broke
    #    silently on custom --port) ─────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # ── Static files (CSS, JS, vendor) ──────────────────────────────────────
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ── WebUI routes ─────────────────────────────────────────────────────────
    from webui.routes import pages, api, sync, preflight
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(sync.router)
    app.include_router(preflight.router)  # [v1.7] pre-flight checks

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
