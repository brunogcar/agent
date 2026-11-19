"""webui/routes/api.py — JSON data routes + HTMX partials.

[WebUI v1.2] Returns JSON for Chart.js + HTML fragments for HTMX swaps.

Routes:
  GET /api/webui/search?q=...               → ticker search (HTML fragment)
  GET /api/webui/company/{ticker}/header    → identity card (HTML fragment)
  GET /api/webui/company/{ticker}/ratios    → valuation ratios (JSON)
  GET /api/webui/company/{ticker}/price-chart?range=1A  → price series (JSON)
  GET /api/webui/company/{ticker}/candlestick?range=1A  → OHLCV + MAs (JSON)
  GET /api/webui/company/{ticker}/price-data → full price data (JSON)
  GET /api/webui/company/{ticker}/tab/{tab} → tab content (HTML fragment)
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from webui.i18n import negotiate_locale, t
from webui.services.company import CompanyService
from webui.services.price import PriceService
from webui.services.financials import FinancialsService

router = APIRouter(prefix="/api/webui", tags=["webui-api"])

_company_service = CompanyService()
_price_service = PriceService()
_financials_service = FinancialsService()

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
    """Identity card — HTML fragment for HTMX swap (persistent header)."""
    header = _company_service.header(ticker.upper())
    locale = _locale(request)
    return _templates.TemplateResponse(
        request,
        "partials/identity_card.html",
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
    # Range → years (fractional for months)
    range_map = {
        "1M": 1/12,      # ~30 days
        "3M": 0.25,      # ~91 days
        "6M": 0.5,       # ~183 days
        "1A": 1,         # 365 days
        "5A": 5,         # 1825 days
        "10A": 10,       # 3650 days
        "Tudo": 30,      # all available data
    }
    years = range_map.get(range, 1)
    series = _company_service.price_series(ticker.upper(), years=years)
    return JSONResponse({
        "labels": [p.get("date", "") for p in series],
        "prices": [p.get("close") for p in series],
    })


@router.get("/company/{ticker}/candlestick")
async def company_candlestick(ticker: str, range: str = Query("1A")):
    """OHLCV + moving averages — JSON for the candlestick chart."""
    range_map = {
        "1M": 1/12, "3M": 0.25, "6M": 0.5, "1A": 1, "5A": 5, "10A": 10, "Tudo": 30,
    }
    years = range_map.get(range, 1)
    data = _price_service.ohlcv_with_mas(ticker.upper(), years=years)
    return JSONResponse(data)


@router.get("/company/{ticker}/price-data")
async def company_price_data(ticker: str):
    """Full price data — JSON for the Preço tab (snapshot, returns, histogram)."""
    data = _price_service.price_data(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/indicators")
async def company_indicators(ticker: str):
    """Technical indicators — JSON for the Indicadores subtab (RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R)."""
    data = _price_service.indicators(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/volatility")
async def company_volatility(ticker: str):
    """Volatility data — JSON for the Volatilidade subtab (Bollinger Bands + rolling vol)."""
    data = _price_service.volatility(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/volume")
async def company_volume(ticker: str):
    """Volume data — JSON for the Volume subtab (volume bars + trade count + contracts)."""
    data = _price_service.volume(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/fibonacci")
async def company_fibonacci(ticker: str):
    """Fibonacci data — JSON for the Fibonacci subtab (swing levels + trade setups)."""
    data = _price_service.fibonacci(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/financials-overview")
async def company_financials_overview(ticker: str):
    """Financials overview data — annual + quarterly + ratios + risk metrics."""
    data = _financials_service.overview(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/financials-statements")
async def company_financials_statements(
    ticker: str,
    period: str = Query("annual"),
    periods: int = Query(10),
):
    """Financial statements — ALL 5 (BPA/BPP/DRE/DFC/DVA) in ONE payload.

    [WebUI v1.3 fix 1] Single SQL pass; quarterly values are STANDALONE quarters.
    The client switches Completo/BPA/BPP/DRE/DFC/DVA views without refetching.
    """
    data = _financials_service.statements(ticker.upper(), period=period, periods=periods)
    return JSONResponse(data)


@router.get("/company/{ticker}/tab/{tab}", response_class=HTMLResponse)
async def company_tab_fragment(request: Request, ticker: str, tab: str):
    """Tab content — HTML fragment for HTMX swap."""
    locale = _locale(request)
    ticker = ticker.upper()
    if tab == "visao_geral":
        header = _company_service.header(ticker)
        return _templates.TemplateResponse(
            request,
            "partials/tab_visao_geral.html",
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
    elif tab == "preco":
        return _templates.TemplateResponse(
            request,
            "partials/tab_preco.html",
            {"ticker": ticker,
             "t": lambda key, **fmt: t(key, locale=locale, **fmt)},
        )
    elif tab == "financials":
        return _templates.TemplateResponse(
            request,
            "partials/tab_financials.html",
            {"ticker": ticker,
             "t": lambda key, **fmt: t(key, locale=locale, **fmt)},
        )
    else:
        return HTMLResponse(f"<div>Tab '{tab}' not implemented yet</div>")
