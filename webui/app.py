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

[v1.20] THE SYSTEM SURFACE:
  - RequestLoggingMiddleware (pure ASGI — SSE-safe) feeds every request
    (method/path/status/duration) into the system log ring buffer; a
    RingBufferHandler on the root logger captures WARNING+ Python
    records (unhandled ASGI exceptions included). Both live in
    webui/services/syslog.py with the 📜 drawer's data.
  - webui/routes/system.py mounts /api/webui/logs(+/stream) and
    /api/webui/settings(+/PUT) — the schema-driven settings store
    (webui/services/settings.py, memory_db/webui_settings.json).
  - The lifespan now ALSO: logs its steps to the system log, honors
    sync.auto_on_startup (sync the stale sources at boot — the
    "Sincronizar tudo" semantics), and starts the periodic auto-sync
    scheduler (sync.schedule_hours; 0 = off) unless --no-sync.
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


def _syslog():
    """Lazy import — avoids import cycles during package init."""
    from webui.services.syslog import syslog
    return syslog


def _settings():
    from webui.services.settings import settings_service
    return settings_service()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: startup schema self-heal + freshness check + shutdown.

    The freshness check never syncs (logs stale sources only).
    WEBUI_NO_SYNC=1 (set by `python webui.py --no-sync`) skips it.
    """
    # [v1.18] Startup schema self-heal for the acoes evolution store.
    # v1.17 added stocks_history to the acoes catalog's CREATE TABLE IF NOT
    # EXISTS script — but the table only materialized on the first ddm-acoes
    # SYNC after the upgrade, so the preflight panel kept showing "tabelas
    # ausentes: stocks_history" on DBs last synced by a pre-v1.17 process
    # (a stale server that was never restarted can even re-sync without
    # creating it — the running code is the old one). Ensuring the schema
    # AT BOOT closes the gap: the table exists as soon as the server
    # starts, the diagnostic clears without a sync, and the NEXT sync
    # fills it (the v2 sync engine still preserves the previous `stocks`
    # snapshot into it on the way). Idempotent (CREATE IF NOT EXISTS,
    # ~5ms); only runs when the DB already exists (a fresh install keeps
    # the "arquivo não encontrado" preflight message — that's a sync
    # hint, not a migration case); failures log to stderr and never block
    # startup (the preflight panel remains the reporter).
    try:
        from data_sources.ddm.acoes.catalog import (
            connect as _acoes_connect, db_path as _acoes_db_path,
            ensure_schema as _acoes_ensure_schema,
        )
        if _acoes_db_path().exists():
            _conn = _acoes_connect(read_only=False)
            try:
                _acoes_ensure_schema(_conn)
            finally:
                _conn.close()
            print("[webui] Startup: acoes schema ensured (stocks_history)",
                  file=sys.stderr)
    except Exception as e:  # pragma: no cover — never block startup
        print(f"[webui] Startup: acoes schema ensure skipped ({e})",
              file=sys.stderr)

    if os.environ.get("WEBUI_NO_SYNC", "") == "1":
        print("[webui] Startup freshness check skipped (--no-sync)", file=sys.stderr)
        _syslog().log("info", "startup",
                      "WebUI iniciado (verificação e agenda de sync desligadas — --no-sync)")
    else:
        print("[webui] Startup: freshness check", file=sys.stderr)
        _syslog().log("info", "startup", "WebUI iniciado — verificando fontes…")

        def _check():
            try:
                # Reuse the sync router's service instance (the app used to
                # create a 3rd SyncService here — routes had two more).
                from webui.routes.sync import _sync_service
                fresh = _sync_service.freshness()
                stale = [k for k, v in fresh.items() if v.get("stale")]
                if stale:
                    msg = f"{len(stale)} fontes desatualizadas: {', '.join(stale)}"
                    print(f"[webui] {msg}", file=sys.stderr)
                    _syslog().log("warning", "startup", msg)
                    # [v1.20] sync.auto_on_startup — the "Sincronizar tudo"
                    # semantics at boot (stale sources only, background
                    # threads, deduped per source). Off by default.
                    if _settings().get("sync.auto_on_startup", False):
                        res = _sync_service.trigger_sync_all(stale_only=True)
                        n = len(res.get("started", []))
                        _syslog().log("info", "startup",
                                      f"Sincronização automática ao iniciar: {n} fonte(s)"
                                      f" em andamento")
                else:
                    print("[webui] All sources fresh", file=sys.stderr)
                    _syslog().log("info", "startup", "Todas as fontes atualizadas")
            except Exception as e:
                print(f"[webui] Freshness check failed: {e}", file=sys.stderr)
                _syslog().log("error", "startup", f"Falha na verificação de fontes: {e}")

        threading.Thread(target=_check, daemon=True).start()

        # [v1.20] Periodic auto-sync scheduler (sync.schedule_hours; 0 =
        # off). Daemon thread with an Event-based stop; the interval is
        # re-read every cycle so a settings change applies without a
        # restart. Skipped entirely under --no-sync.
        from webui.routes.sync import _sync_service
        _sync_service.start_scheduler()

    yield

    print("[webui] Shutdown", file=sys.stderr)
    _syslog().log("info", "startup", "WebUI encerrado")
    try:
        from webui.routes.sync import _sync_service
        _sync_service.stop_scheduler()
    except Exception:
        pass


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

    # ── [v1.20] System log capture: requests + Python logging WARNING+ ──────
    # Outermost middleware (last added = first to see the request) so even
    # TrustedHost rejections are logged. Pure ASGI — SSE streams untouched.
    from webui.services.syslog import (
        RequestLoggingMiddleware, attach_logging_handler,
    )
    app.add_middleware(RequestLoggingMiddleware)
    attach_logging_handler()

    # ── WebUI routes ─────────────────────────────────────────────────────────
    from webui.routes import pages, api, sync, preflight, system, portfolio
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(sync.router)
    app.include_router(preflight.router)  # [v1.7] pre-flight checks
    app.include_router(system.router)     # [v1.20] logs + settings
    app.include_router(portfolio.router)  # [v1.21] carteira (portfolio)

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
