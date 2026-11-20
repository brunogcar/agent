"""webui/routes/sync.py — sync status + SSE stream.

[WebUI v1] Server-Sent Events for sync progress. Per LLM consensus (9/9
reviewers): SSE, NOT WebSocket. One-way server→client, auto-reconnects,
works through proxies, no protocol library.

[WebUI v1.5] HARDENING (sync-page repair):
  - /status now returns an HTML PARTIAL (partials/sync_status.html) — the
    old JSON response was swapped into the page with hx-swap=innerHTML,
    painting raw JSON on the Sync page and Dashboard ribbon. /status.json
    keeps the JSON shape for programmatic use.
  - POST /{source} validates against the sync_guard allow-list (400 +
    PT-BR message for unknown sources) and returns the job dict (including
    the already-running dedupe case).
  - /stream sends an explicit retry: 3000 so the reconnect interval is
    visible in the contract.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from webui.services.sync import SyncService, syncable_sources
from webui.templating import templates

router = APIRouter(prefix="/api/webui/sync", tags=["webui-sync"])

_sync_service = SyncService()


def _fmt_ts(ts: str) -> str:
    """ISO timestamp → DD/MM/YYYY HH:MM (pt-BR)."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return ts


def _status_rows() -> list[dict]:
    """Freshness rows for the status partial (source, badge, last sync)."""
    fresh = _sync_service.freshness()
    syncable = set(syncable_sources())
    rows = []
    for source, info in fresh.items():
        rows.append({
            "source": source,
            "last_sync": _fmt_ts(info.get("last_sync", "")),
            "stale": bool(info.get("stale")),
            "can_sync": source in syncable,
        })
    return rows


@router.get("/status", response_class=HTMLResponse)
async def sync_status(request: Request):
    """Freshness table — HTML partial for HTMX swap (Sync page + Dashboard)."""
    return templates.TemplateResponse(
        request,
        "partials/sync_status.html",
        {"rows": _status_rows()},
    )


@router.get("/status.json")
async def sync_status_json():
    """Freshness snapshot — JSON (programmatic use)."""
    return JSONResponse(_sync_service.freshness())


@router.post("/all")
async def trigger_sync_all():
    """[v1.5 fix1] Trigger background syncs for every syncable source.

    Stale sources only (fresh within 24h are skipped) — one click brings
    everything up to date without re-downloading data that is current.
    Returns {started: [jobs], skipped_fresh, already_running, total_sources}.

    NOTE: this route MUST stay ABOVE POST /{source} — Starlette matches in
    registration order, and "/all" would otherwise be captured as a source
    name and rejected with 400.
    """
    return JSONResponse(_sync_service.trigger_sync_all(stale_only=True))


@router.post("/{source}")
async def trigger_sync(source: str):
    """Trigger a background sync for one source. Returns the job dict.

    400 + PT-BR message for sources outside the sync_guard allow-list.
    A second click while a sync is running returns the existing job with
    already_running=True (no duplicate concurrent syncs).
    """
    try:
        job = _sync_service.trigger_sync(source)
    except ValueError:
        return JSONResponse(
            {"_error": f"Fonte de dados desconhecida: '{source}'"},
            status_code=400,
        )
    return JSONResponse(job)


@router.get("/stream")
async def sync_stream(request: Request):
    """SSE stream of sync events. Auto-reconnects on disconnect."""
    queue = _sync_service.subscribe()

    async def event_generator():
        try:
            # Explicit reconnect interval (ms) — makes the contract visible.
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment (prevents proxy timeout)
                    yield ": keepalive\n\n"
        finally:
            _sync_service.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )
