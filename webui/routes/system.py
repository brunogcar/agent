"""webui/routes/system.py — the system surface: logs + settings.

[v1.20] Two cohesive subtrees on ONE router (the sync.py / preflight.py
precedent of dedicated route modules):

  GET  /api/webui/logs            → ring-buffer snapshot (or ?after=<id> for
                                    the incremental tail — same entries the
                                    SSE stream pushes)
  GET  /api/webui/logs/stream     → SSE: one "snapshot" event (the current
                                    buffer) + "logs" batches every ~1s. The
                                    Sync page's SSE precedent, minus the
                                    subscriber registry — the buffer is
                                    PULLED here (worker threads never push
                                    into this stream), so a plain poll loop
                                    inside the generator is enough.
  GET  /api/webui/settings        → schema + current values (the settings
                                    page renders the form from this)
  PUT  /api/webui/settings        → validate + persist a {key: value} patch
                                    (all-or-nothing; PT-BR errors per key)

Handler style follows api.py: plain `def` for the blocking file/JSON work
(threadpool — never blocks the loop), `async def` only for the SSE stream.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from webui.services.settings import settings_service
from webui.services.syslog import syslog

router = APIRouter(prefix="/api/webui", tags=["webui-system"])


# ── system log ────────────────────────────────────────────────────────────────
@router.get("/logs")
def get_logs(after: int = Query(0, ge=0), limit: int = Query(300, ge=1, le=5000)):
    """Ring-buffer entries. ``after=0`` → snapshot (last ``limit``);
    ``after=<id>`` → only the entries after that id (empty list = caught
    up — the incremental tail the SSE stream also pushes).
    """
    entries = syslog.since(after) if after > 0 else syslog.snapshot(limit)
    return JSONResponse({"entries": entries})


@router.get("/logs/stream")
async def logs_stream(request: Request):
    """SSE system-log tail (the 📜 drawer's live feed).

    Connect → the whole current buffer as one ``snapshot`` event, then a
    ~1s poll pushes ``logs`` batches (plus a keepalive comment every ~15s
    of silence so proxies don't time the stream out). Disconnect (drawer
    closed) ends the generator — no permanent connection, no subscriber
    bookkeeping.
    """
    async def event_generator():
        try:
            yield "retry: 3000\n\n"
            entries = syslog.snapshot()
            last_id = entries[-1]["id"] if entries else 0
            if entries:
                yield f"event: snapshot\ndata: {json.dumps(entries)}\n\n"
            idle = 0
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(1.0)
                entries = syslog.since(last_id)
                if entries:
                    last_id = entries[-1]["id"]
                    idle = 0
                    yield f"event: logs\ndata: {json.dumps(entries)}\n\n"
                else:
                    idle += 1
                    if idle >= 15:
                        idle = 0
                        yield ": keepalive\n\n"
        except asyncio.CancelledError:  # client gone — expected on close
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── settings ──────────────────────────────────────────────────────────────────
@router.get("/settings")
def get_settings(request: Request):
    """Schema + current values — the settings page auto-renders from this.

    ui.theme / ui.locale are seeded from the request COOKIES (the cookie
    is the single source of truth for those — the file only mirrors the
    last save).
    """
    svc = settings_service()
    overrides = {
        "ui.theme": request.cookies.get("webui_theme", "dark"),
        "ui.locale": request.cookies.get("webui_locale", "pt-BR"),
    }
    return JSONResponse({
        "sections": svc.as_schema(overrides=overrides),
        "values": {**svc.values(), **overrides},
    })


@router.put("/settings")
async def put_settings(request: Request):
    """Persist a {key: value} patch (JSON body). All-or-nothing.

    ui.theme / ui.locale additionally get a Set-Cookie on the response —
    the client reloads after saving and the whole shell (FOUC script,
    negotiate_locale, data-theme) picks them up; the cookie stays the
    single source of truth, the JSON file mirrors the last save.

    async def: the body must be awaited (the file write itself is a
    sub-millisecond atomic replace of a tiny JSON).
    """
    # [v1.22 CSRF] request.json() parses ANY content type; demanding
    # application/json means a cross-site text/plain POST (a CORS-simple
    # request, no preflight) can never reach the store. (The app-level
    # CrossSiteGuardMiddleware covers Sec-Fetch-Site/Origin globally.)
    if "application/json" not in (request.headers.get("content-type")
                                  or "").lower():
        patch = None
    else:
        try:
            patch = await request.json()
        except Exception:
            patch = None
    if not isinstance(patch, dict) or not patch:
        return JSONResponse(
            {"_error": "Corpo inválido — esperado um objeto {chave: valor}."},
            status_code=400,
        )

    svc = settings_service()
    result = svc.update(patch)
    if not result.get("ok"):
        return JSONResponse(
            {"_error": "Algumas configurações são inválidas.",
             "errors": result.get("errors", {})},
            status_code=400,
        )

    applied = result.get("applied", [])
    response = JSONResponse(result)
    if "ui.theme" in applied:
        response.set_cookie("webui_theme", str(result["values"]["ui.theme"]),
                            path="/", max_age=31536000)
    if "ui.locale" in applied:
        response.set_cookie("webui_locale", str(result["values"]["ui.locale"]),
                            path="/", max_age=31536000)
    return response
