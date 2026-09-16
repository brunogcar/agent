"""webui/routes/api.py — JSON data routes + HTMX partials.

[WebUI v1] Returns JSON for Chart.js + HTML fragments for HTMX swaps.
The HTML fragments are Jinja2 partials (no <html> wrapper).

Routes:
  GET /api/webui/search?q=...               → ticker search (HTML fragment)
  GET /api/webui/company/{ticker}/header    → company header (HTML fragment)
  GET /api/webui/company/{ticker}/ratios    → valuation ratios (JSON)
  GET /api/webui/company/{ticker}/price-chart?range=1A  → price series (JSON)
  GET /api/webui/company/{ticker}/tab/{tab} → tab content (HTML fragment)
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from webui.i18n import negotiate_locale, t
from webui.services.company import CompanyService

router = APIRouter(prefix="/api/webui", tags=["webui-api"])

_company_service = CompanyService()

# We'll import the templates from pages.py to share the Jinja2 env
from fastapi.templating import Jinja2Templates
_templates = Jinja2Templates(directory="webui/templates")


def _locale(request: Request) -> str:
    return negotiate_locale(
        query_lang=request.query_params.get("lang"),
        cookie_lang=request.cookies.get("webui_locale"),
        accept_header=request.headers.get("accept-language", ""),
    )


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("")):
    """Ticker search — returns HTML fragment for HTMX swap."""
    results = _company_service.search(q)
    locale = _locale(request)
    # Render a partial template with the results
    return _templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {
            "results": results,
            "t": lambda key, **fmt: t(key, locale=locale, **fmt),
        },
    )


@router.get("/company/{ticker}/header", response_class=HTMLResponse)
async def company_header_fragment(request: Request, ticker: str):
    """Company header — HTML fragment for HTMX swap."""
    header = _company_service.header(ticker.upper())
    locale = _locale(request)
    return _templates.TemplateResponse(
        request,
        "partials/company_header.html",
        {
            "header": header,
            "t": lambda key, **fmt: t(key, locale=locale, **fmt),
        },
    )


@router.get("/company/{ticker}/ratios")
async def company_ratios(ticker: str):
    """Valuation ratios — JSON for the ratios tab."""
    ratios = _company_service.ratios(ticker.upper())
    return JSONResponse(ratios)


@router.get("/company/{ticker}/price-chart")
async def company_price_chart(ticker: str, range: str = Query("1A")):
    """Price series — JSON for Chart.js."""
    years_map = {"1M": 1/12, "6M": 0.5, "1A": 1, "5A": 5, "Tudo": 10}
    years = years_map.get(range, 1)
    series = _company_service.price_series(ticker.upper(), years=int(years) if years >= 1 else 1)
    return JSONResponse({
        "labels": [p.get("date", "") for p in series],
        "prices": [p.get("close") for p in series],
    })


@router.get("/company/{ticker}/tab/{tab}", response_class=HTMLResponse)
async def company_tab_fragment(request: Request, ticker: str, tab: str):
    """Tab content — HTML fragment for HTMX swap."""
    locale = _locale(request)
    ticker = ticker.upper()
    if tab == "overview":
        header = _company_service.header(ticker)
        return _templates.TemplateResponse(
            request,
            "partials/tab_overview.html",
            {"ticker": ticker, "header": header,
             "t": lambda key, **fmt: t(key, locale=locale, **fmt)},
        )
    elif tab == "valuation":
        ratios = _company_service.ratios(ticker)
        return _templates.TemplateResponse(
            request,
            "partials/tab_valuation.html",
            {"ticker": ticker, "ratios": ratios,
             "t": lambda key, **fmt: t(key, locale=locale, **fmt)},
        )
    else:
        return HTMLResponse(f"<div>Tab '{tab}' not implemented yet</div>")
