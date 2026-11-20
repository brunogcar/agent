"""webui/routes/api.py — JSON data routes + HTMX partials.

[WebUI v1.2] Returns JSON for Chart.js + HTML fragments for HTMX swaps.
[WebUI v1.4] Valuation tab: 5 lazy JSON endpoints (one per subtab) + the
  tab shell fragment no longer fetches ratios server-side.
[WebUI v1.5] HARDENING:
  - Ticker path params validated with a B3 regex (Annotated Path pattern)
    → 422 for garbage BEFORE it reaches engines/templates/JS strings. This
    kills the reflected-XSS class at the route boundary.
  - Unknown tab names → 404 PT-BR PLAIN TEXT (the old fallback
    interpolated the raw `tab` path param into an HTMLResponse —
    reflected XSS).
  - Handlers are plain `def` (NOT `async def`) so FastAPI runs the
    blocking SQLite/engine work in its threadpool — the old async
    handlers froze the event loop (and the SSE stream) during report
    builds.
  - Dead endpoints removed (/ratios, /price-chart — no client references
    since v1.2).
  - One shared Jinja env (webui/templating.py) resolved from __file__.
  - `range` validated against the map (unknown → _error, not silent 1A).

Routes:
  GET /api/webui/search?q=...               → ticker search (HTML fragment)
  GET /api/webui/company/{ticker}/header    → identity card (HTML fragment)
  GET /api/webui/company/{ticker}/candlestick?range=1A  → OHLCV + MAs (JSON)
  GET /api/webui/company/{ticker}/price-data → full price data (JSON)
  GET /api/webui/company/{ticker}/indicators → RSI/MACD/Stoch/OBV/ADX/CCI/W%R (JSON)
  GET /api/webui/company/{ticker}/volatility → Bollinger + rolling vol (JSON)
  GET /api/webui/company/{ticker}/volume     → volume/trades/contracts (JSON)
  GET /api/webui/company/{ticker}/fibonacci  → swings + setups (JSON)
  GET /api/webui/company/{ticker}/financials-overview   → Financeiro Visão Geral (JSON)
  GET /api/webui/company/{ticker}/financials-statements → Demonstrações (JSON)
  GET /api/webui/company/{ticker}/valuation-overview    → Valuation Visão Geral (JSON)
  GET /api/webui/company/{ticker}/valuation-multiples   → Valuation Múltiplos (JSON)
  GET /api/webui/company/{ticker}/valuation-intrinsic   → Valor Intrínseco (JSON)
  GET /api/webui/company/{ticker}/valuation-fundamentals→ Fundamentos (JSON)
  GET /api/webui/company/{ticker}/valuation-all         → Todas as métricas (JSON)
  GET /api/webui/company/{ticker}/tab/{tab} → tab content (HTML fragment)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from webui.i18n import negotiate_locale, t
from webui.services.company import CompanyService
from webui.services.price import PriceService
from webui.services.financials import FinancialsService
from webui.services.valuation import ValuationService
from webui.templating import templates

router = APIRouter(prefix="/api/webui", tags=["webui-api"])

_company_service = CompanyService()
_price_service = PriceService()
_financials_service = FinancialsService()
_valuation_service = ValuationService()

# ── [WebUI v1.5] Ticker validation ──────────────────────────────────────────
# B3 symbols: 4-6 letters + 1-2 digits + optional trailing letter
# (PETR4, BOVA11, UNIT11, AAPL34, …). Validated at the route boundary so
# garbage never reaches the engines, SQL LIKE patterns, Jinja contexts or
# client JS strings. FastAPI returns 422 automatically on mismatch.
Ticker = Annotated[str, Path(pattern=r"^[A-Za-z]{4,6}\d{1,2}[A-Za-z]?$")]

# Tabs with a rendered partial (dividends/historical are future work —
# company.html hides their buttons until they exist).
_ALLOWED_TABS = {"visao_geral", "valuation", "preco", "financials"}

# Shared range map (was duplicated ×2 and silently fell back to 1A on typos).
_RANGE_YEARS = {
    "1M": 1 / 12,   # ~30 days
    "3M": 0.25,     # ~91 days
    "6M": 0.5,      # ~183 days
    "1A": 1,        # 365 days
    "5A": 5,        # 1825 days
    "10A": 10,      # 3650 days
    "Tudo": 30,     # all available data
}


def _locale(request: Request) -> str:
    return negotiate_locale(
        query_lang=request.query_params.get("lang"),
        cookie_lang=request.cookies.get("webui_locale"),
        accept_header=request.headers.get("accept-language", ""),
    )


def _tr(request: Request):
    locale = _locale(request)
    return lambda key, **fmt: t(key, locale=locale, **fmt)


@router.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = Query("")):
    """Ticker search — returns HTML fragment for HTMX swap."""
    results = _company_service.search(q)
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {"results": results, "t": _tr(request)},
    )


@router.get("/company/{ticker}/header", response_class=HTMLResponse)
def company_header_fragment(request: Request, ticker: Ticker):
    """Identity card — HTML fragment for HTMX swap (persistent header)."""
    header = _company_service.header(ticker.upper())
    return templates.TemplateResponse(
        request,
        "partials/identity_card.html",
        {"header": header, "t": _tr(request)},
    )


def _range_years(range_: str) -> float:
    """Validated range → years. Raises ValueError on unknown range keys."""
    if range_ not in _RANGE_YEARS:
        raise ValueError(f"range inválido: {range_}")
    return _RANGE_YEARS[range_]


@router.get("/company/{ticker}/candlestick")
def company_candlestick(ticker: Ticker, range_: str = Query("1A", alias="range")):
    """OHLCV + moving averages — JSON for the candlestick chart."""
    try:
        years = _range_years(range_)
    except ValueError as e:
        return JSONResponse({"_error": str(e)})
    data = _price_service.ohlcv_with_mas(ticker.upper(), years=years)
    return JSONResponse(data)


@router.get("/company/{ticker}/price-data")
def company_price_data(ticker: Ticker):
    """Full price data — JSON for the Preço tab (snapshot, returns, histogram)."""
    data = _price_service.price_data(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/indicators")
def company_indicators(ticker: Ticker):
    """Technical indicators — JSON for the Indicadores subtab."""
    data = _price_service.indicators(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/volatility")
def company_volatility(ticker: Ticker):
    """Volatility data — JSON for the Volatilidade subtab."""
    data = _price_service.volatility(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/volume")
def company_volume(ticker: Ticker):
    """Volume data — JSON for the Volume subtab."""
    data = _price_service.volume(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/fibonacci")
def company_fibonacci(ticker: Ticker):
    """Fibonacci data — JSON for the Fibonacci subtab."""
    data = _price_service.fibonacci(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/financials-overview")
def company_financials_overview(ticker: Ticker):
    """Financials overview data — annual + quarterly + ratios + risk metrics."""
    data = _financials_service.overview(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/financials-statements")
def company_financials_statements(
    ticker: Ticker,
    period: str = Query("annual"),
    periods: int = Query(10),
):
    """Financial statements — ALL 5 (BPA/BPP/DRE/DFC/DVA) in ONE payload."""
    data = _financials_service.statements(ticker.upper(), period=period, periods=periods)
    return JSONResponse(data)


@router.get("/company/{ticker}/valuation-overview")
def company_valuation_overview(ticker: Ticker):
    """[WebUI v1.4] Valuation Visão Geral — KPIs + heatmap + radar + blocks."""
    data = _valuation_service.overview(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/valuation-multiples")
def company_valuation_multiples(ticker: Ticker):
    """[WebUI v1.4] Valuation Múltiplos — grouped tables + comparativo + 5Y history."""
    data = _valuation_service.multiples(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/valuation-intrinsic")
def company_valuation_intrinsic(ticker: Ticker):
    """[WebUI v1.4] Valuation Valor Intrínseco — DCF + TIR + sensitivity."""
    data = _valuation_service.intrinsic(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/valuation-fundamentals")
def company_valuation_fundamentals(ticker: Ticker):
    """[WebUI v1.4] Valuation Fundamentos — rentabilidade, liquidez, alavancagem."""
    data = _valuation_service.fundamentals(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/valuation-all")
def company_valuation_all(ticker: Ticker):
    """[WebUI v1.4] Valuation Todas as métricas — every ratio grouped by category."""
    data = _valuation_service.all_metrics(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/tab/{tab}", response_class=HTMLResponse)
def company_tab_fragment(request: Request, ticker: Ticker, tab: str):
    """Tab content — HTML fragment for HTMX swap.

    [WebUI v1.5] `tab` is validated against the allow-list; unknown tabs
    get a 404 PLAIN-TEXT PT-BR message. The old fallback interpolated the
    raw path param into HTMLResponse — reflected XSS
    (/tab/%3Cimg%20src%3Dx%20onerror%3D…%3E executed).
    """
    if tab not in _ALLOWED_TABS:
        return PlainTextResponse(
            f"Aba '{tab}' não implementada.", status_code=404
        )
    tr = _tr(request)
    ticker = ticker.upper()
    if tab == "visao_geral":
        header = _company_service.header(ticker)
        return templates.TemplateResponse(
            request,
            "partials/tab_visao_geral.html",
            {"ticker": ticker, "header": header, "t": tr},
        )
    elif tab == "valuation":
        # [WebUI v1.4] Shell only — subtabs fetch their own JSON endpoints
        # lazily (valuation-overview/-multiples/-intrinsic/-fundamentals/-all).
        return templates.TemplateResponse(
            request,
            "partials/tab_valuation.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "preco":
        return templates.TemplateResponse(
            request,
            "partials/tab_preco.html",
            {"ticker": ticker, "t": tr},
        )
    else:  # financials
        return templates.TemplateResponse(
            request,
            "partials/tab_financials.html",
            {"ticker": ticker, "t": tr},
        )
