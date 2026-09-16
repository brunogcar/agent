"""webui/routes/sync.py — sync status + SSE stream.

[WebUI v1] Server-Sent Events for sync progress. Per LLM consensus (9/9
reviewers): SSE, NOT WebSocket. One-way server→client, auto-reconnects,
works through proxies, no protocol library.

Routes:
  GET /api/webui/sync/status   → JSON freshness snapshot
  POST /api/webui/sync/{source} → trigger sync, returns job_id
  GET /api/webui/sync/stream    → SSE stream of sync events
"""
from __future__ import annotations

import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from webui.services.sync import SyncService

router = APIRouter(prefix="/api/webui/sync", tags=["webui-sync"])

_sync_service = SyncService()


@router.get("/status")
async def sync_status():
    """Freshness snapshot for all data sources."""
    return JSONResponse(_sync_service.freshness())


@router.post("/{source}")
async def trigger_sync(source: str):
    """Trigger a background sync for one source. Returns job_id."""
    job_id = _sync_service.trigger_sync(source)
    return JSONResponse({"job_id": job_id, "source": source, "status": "started"})


@router.get("/stream")
async def sync_stream(request: Request):
    """SSE stream of sync events. Auto-reconnects on disconnect."""
    queue = _sync_service.subscribe()

    async def event_generator():
        try:
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
