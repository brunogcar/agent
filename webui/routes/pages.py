"""webui/routes/pages.py — HTML page routes (Jinja2 server-rendered).

[WebUI v1] Returns full HTML pages. HTMX swaps fragments via the /api/webui/*
endpoints in api.py.

[WebUI v1.5] HARDENING:
  - active_tab is now set for EVERY page (dashboard/macro/sync/settings) —
    the sidebar never highlighted the current page before. Company pages
    validate the tab path segment (unknown → redirect to visao_geral).
  - The dead eager header() calls are GONE: company_overview/company_tab
    used to compute the full company header (FCA/CAD/COTAHIST/B3 queries)
    and pass it into a context company.html never rendered — every page
    load paid the cost twice for nothing. The identity card fetches its
    own fragment via HTMX.
  - Handlers are plain `def` (threadpool) — see api.py.
  - One shared Jinja env from webui/templating.py (was CWD-relative ×2).

Routes:
  GET /webui                      → dashboard (home, no ticker)
  GET /webui/company/{ticker}     → company overview
  GET /webui/company/{ticker}/{tab}  → company tab (visao_geral/preco/financials/valuation)
  GET /webui/macro                → macro page
  GET /webui/mercado              → mercado page (DDM dashboards) [v1.12]
  GET /webui/sync                 → sync status page
  GET /webui/settings             → settings page
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from webui.i18n import negotiate_locale, t
from webui.theme import available_themes, render_all_themes_css
from webui.templating import templates

router = APIRouter(prefix="/webui", tags=["webui-pages"])

# Tabs that have a page shell (must match api.py's _ALLOWED_TABS).
# [v1.9] shareholders. [v1.10] insiders.
_PAGE_TABS = {"visao_geral", "preco", "financials", "valuation", "proventos", "options", "shareholders", "insiders"}


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
    }
    ctx.update(extra)
    return ctx


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Home dashboard — market overview, no ticker required."""
    return templates.TemplateResponse(
        request, "pages/dashboard.html", _ctx(request, active_tab="dashboard"),
    )


@router.get("/company/{ticker}", response_class=HTMLResponse)
def company_overview(request: Request, ticker: str):
    """Company overview page (default tab: visao_geral).

    [WebUI v1.5] No eager header() — the identity card fetches its own
    fragment via HTMX (hx-trigger="load"); computing it here doubled the
    FCA/CAD/COTAHIST/B3 query cost per page load for a context value
    company.html never rendered.
    """
    return templates.TemplateResponse(
        request, "pages/company.html",
        _ctx(request, ticker=ticker.upper(), active_tab="visao_geral"),
    )


@router.get("/company/{ticker}/{tab}", response_class=HTMLResponse)
def company_tab(request: Request, ticker: str, tab: str):
    """Company tab page (visao_geral, preco, financials, valuation)."""
    if tab not in _PAGE_TABS:
        # Unknown tab → redirect to the default (Jinja escapes everything,
        # but there's no page shell for arbitrary tab names anyway).
        return RedirectResponse(
            url=f"/webui/company/{ticker.upper()}", status_code=302,
        )
    return templates.TemplateResponse(
        request, "pages/company.html",
        _ctx(request, ticker=ticker.upper(), active_tab=tab),
    )


@router.get("/macro", response_class=HTMLResponse)
def macro_page(request: Request):
    return templates.TemplateResponse(
        request, "pages/macro.html", _ctx(request, active_tab="macro"),
    )


@router.get("/mercado", response_class=HTMLResponse)
def mercado_page(request: Request):
    """[v1.12] Mercado page — the DDM dashboards' home.

    Market-level data from dadosdemercado.com.br (Boletim Focus now;
    dividends, índices, fluxo, inflação and juros as later families),
    next to Macro (realized BCB SGS indicators). Family + subtab shell
    (macro.html pattern, one level deeper — the company page's tab /
    subtab architecture on a standalone page).
    """
    return templates.TemplateResponse(
        request, "pages/mercado.html", _ctx(request, active_tab="mercado"),
    )


@router.get("/sync", response_class=HTMLResponse)
def sync_page(request: Request):
    return templates.TemplateResponse(
        request, "pages/sync.html", _ctx(request, active_tab="sync"),
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(
        request, "pages/settings.html", _ctx(request, active_tab="settings"),
    )
