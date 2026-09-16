"""webui/routes/pages.py — HTML page routes (Jinja2 server-rendered).

[WebUI v1] Returns full HTML pages. HTMX swaps fragments via the /api/webui/*
endpoints in api.py.

Routes:
  GET /webui                      → dashboard (home, no ticker)
  GET /webui/company/{ticker}     → company overview
  GET /webui/company/{ticker}/{tab}  → company tab (valuation, financials, etc.)
  GET /webui/macro                → macro page
  GET /webui/sync                 → sync status page
  GET /webui/settings             → settings page
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webui.i18n import negotiate_locale, t
from webui.theme import available_themes, render_all_themes_css
from webui.services.company import CompanyService
from webui.services.sync import SyncService

router = APIRouter(prefix="/webui", tags=["webui-pages"])
templates = Jinja2Templates(directory="webui/templates")

# Service singletons (created once, reused)
_company_service = CompanyService()
_sync_service = SyncService()


def _ctx(request: Request, **extra) -> dict:
    """Build the Jinja2 context with i18n + theme + request."""
    locale = negotiate_locale(
        query_lang=request.query_params.get("lang"),
        cookie_lang=request.cookies.get("webui_locale"),
        accept_header=request.headers.get("accept-language", ""),
    )
    theme = request.cookies.get("webui_theme", "dark")
    ctx = {
        "request": request,
        "locale": locale,
        "theme": theme,
        "themes": available_themes(),
        "theme_css": render_all_themes_css(),
        "t": lambda key, **fmt: t(key, locale=locale, **fmt),
        "_": lambda key, **fmt: t(key, locale=locale, **fmt),
        "company_service": _company_service,
        "sync_service": _sync_service,
    }
    ctx.update(extra)
    return ctx


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Home dashboard — market overview, no ticker required."""
    return templates.TemplateResponse(request, "pages/dashboard.html", _ctx(request))


@router.get("/company/{ticker}", response_class=HTMLResponse)
async def company_overview(request: Request, ticker: str):
    """Company overview page (default tab)."""
    header = _company_service.header(ticker.upper())
    return templates.TemplateResponse(
        request, "pages/company.html",
        _ctx(request, ticker=ticker.upper(), header=header, active_tab="overview"),
    )


@router.get("/company/{ticker}/{tab}", response_class=HTMLResponse)
async def company_tab(request: Request, ticker: str, tab: str):
    """Company tab page (valuation, financials, dividends, historical)."""
    header = _company_service.header(ticker.upper())
    return templates.TemplateResponse(
        request, "pages/company.html",
        _ctx(request, ticker=ticker.upper(), header=header, active_tab=tab),
    )


@router.get("/macro", response_class=HTMLResponse)
async def macro_page(request: Request):
    return templates.TemplateResponse(request, "pages/macro.html", _ctx(request))


@router.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    freshness = _sync_service.freshness()
    return templates.TemplateResponse(
        request, "pages/sync.html", _ctx(request, freshness=freshness),
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "pages/settings.html", _ctx(request))
