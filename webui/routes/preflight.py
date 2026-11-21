"""webui/routes/preflight.py — pre-flight check endpoints.

[v1.7] Surfaces PreflightService in the UI:
  GET /api/webui/preflight         → full report (JSON, programmatic)
  GET /api/webui/preflight/panel   → HTML partial — Sync page card
  GET /api/webui/preflight/banner  → HTML partial — Dashboard one-liner

Same pattern as webui/routes/sync.py: HTML partials for HTMX swaps
(hx-trigger="load"), JSON for scripts. Checks run per request (cheap —
file stats, pragmas, MAX(rowid) probes).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from webui.services.preflight import PreflightService
from webui.templating import templates

router = APIRouter(prefix="/api/webui/preflight", tags=["webui-preflight"])

_preflight_service = PreflightService()


@router.get("/")
def preflight_report():
    """Full pre-flight report — JSON (/api/webui/preflight/; the slash-less
    variant 307-redirects here)."""
    return JSONResponse(_preflight_service.run())


@router.get("/panel", response_class=HTMLResponse)
def preflight_panel(request: Request):
    """Grouped checks card — HTML partial for the Sync page."""
    report = _preflight_service.run()
    return templates.TemplateResponse(
        request,
        "partials/preflight_panel.html",
        {"report": report},
    )


@router.get("/banner", response_class=HTMLResponse)
def preflight_banner(request: Request):
    """One-line summary — HTML partial for the Dashboard."""
    report = _preflight_service.run()
    return templates.TemplateResponse(
        request,
        "partials/preflight_banner.html",
        {"report": report},
    )
