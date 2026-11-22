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
[v1.7] Service singletons come from webui.adapters.registry.service()
  (memoized — the adapters registry dispatches through the SAME
  instances, so PriceService's 60s-TTL OHLCV cache is shared). New
  generic endpoint /company/{ticker}/sections/{key} dispatches any
  registered adapter — the per-family endpoints below remain as
  stable aliases (existing client loaders keep working; new tabs use
  the generic path).
[v1.11] New ticker-less generic endpoint /macro/sections/{key} —
  dispatches the macro:* adapters (market-wide payloads, no company
  scope) through the same registry + contract validation. Unknown keys
  → 404 PT-BR plain text (same pattern as the company endpoint).
[v1.12] New ticker-less generic endpoint /mercado/sections/{key} —
  same dispatch for the mercado:* page families (focus:* now; the
  DDM dashboards dividends/índices/fluxo/inflação/juros as later
  families).
[v1.13] fluxo:* joins the mercado endpoint (4 subtabs — the B3
  investment flow family).
[v1.14] indices:* joins the mercado endpoint (6 subtabs — the B3 index
  composition family: overview + IBOV/SMLL/BDRX/IFIX/IDIV).
[v1.15] inflacao:* joins the mercado endpoint (4 subtabs — the DDM
  price-index family: overview + IGP-M/IPCA/INPC).
[v1.16] juros:* joins the mercado endpoint (4 subtabs — the DDM
  interest-rate family: overview + Selic/Meta Selic/CDI).

Routes:
  GET /api/webui/search?q=...               → ticker search (HTML fragment)
  GET /api/webui/company/{ticker}/header    → identity card (HTML fragment)
  GET /api/webui/company/{ticker}/sections/{key} → ANY registered subtab
        adapter (key = "<family>:<sub>", e.g. valuation:overview,
        financials:demonstracoes?period=quarterly) [v1.7]
  GET /api/webui/macro/sections/{key}       → macro subtabs (ticker-less,
        key = "macro:<sub>": overview/juros/inflacao/cambio/atividade/
        retorno_real/focus/curva) [v1.11]
  GET /api/webui/mercado/sections/{key}     → mercado page subtabs
        (ticker-less; focus: overview/inflacao/atividade/juros/cambio/
        externo/fiscal; fluxo: overview/mensal/anual/por_investidor;
        indices: overview/ibov/smll/bdrx/ifix/idiv; inflacao: overview/
        igpm/ipca/inpc; juros: overview/selic/meta_selic/cdi)
        [v1.12, v1.13, v1.14, v1.15, v1.16]
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
  GET /api/webui/company/{ticker}/proventos-overview    → Proventos Visão Geral (JSON)
  GET /api/webui/company/{ticker}/proventos-historico   → Proventos Histórico completo (JSON)
  GET /api/webui/company/{ticker}/proventos-anual       → Proventos Anual (JSON)
  GET /api/webui/company/{ticker}/tab/{tab} → tab content (HTML fragment)
"""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from webui.adapters.registry import dispatch, has as adapter_has
from webui.i18n import negotiate_locale, t
from webui.services.company import CompanyService
from webui.services.price import PriceService
from webui.services.financials import FinancialsService
from webui.services.valuation import ValuationService
from webui.services.proventos import ProventosService
from webui.templating import templates

router = APIRouter(prefix="/api/webui", tags=["webui-api"])

# [v1.7] Singletons via the adapters registry factory — the generic
# /sections/{key} dispatch path binds the SAME instances (one PriceService
# = one shared OHLCV cache, as intended since v1.5).
def _svc(cls):
    from webui.adapters.registry import service
    return service(cls)


_company_service = _svc(CompanyService)
_price_service = _svc(PriceService)
_financials_service = _svc(FinancialsService)
_valuation_service = _svc(ValuationService)
_proventos_service = _svc(ProventosService)

# ── [WebUI v1.5] Ticker validation ──────────────────────────────────────────
# B3 symbols: 4-6 letters + 1-2 digits + optional trailing letter
# (PETR4, BOVA11, UNIT11, AAPL34, …). Validated at the route boundary so
# garbage never reaches the engines, SQL LIKE patterns, Jinja contexts or
# client JS strings. FastAPI returns 422 automatically on mismatch.
Ticker = Annotated[str, Path(pattern=r"^[A-Za-z]{4,6}\d{1,2}[A-Za-z]?$")]

# [v1.7] Adapter key validation — "<family>:<sub>" (colon is a legal path
# character, RFC 3986). Checked BEFORE dispatch; unknown keys get a 404
# PT-BR plain-text message (same pattern as the tab route — never reflect
# the raw param into HTML).
_ADAPTER_KEY_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_-]+$")

# Tabs with a rendered partial (historical is future work —
# company.html hides its button until it exists). [v1.6] proventos.
# [v1.8] options. [v1.9] shareholders. [v1.10] insiders.
_ALLOWED_TABS = {"visao_geral", "valuation", "preco", "financials", "proventos", "options", "shareholders", "insiders"}

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


@router.get("/company/{ticker}/sections/{key}")
def company_sections(ticker: Ticker, key: str,
                     period: str = Query("annual"),
                     periods: int = Query(10),
                     maturity: str = Query("")):
    """[v1.7] Generic subtab endpoint — dispatches ANY registered adapter.

    Key format "<family>:<sub>" (e.g. valuation:overview,
    proventos:anual, financials:demonstracoes). Params are passed through
    to the adapter (period/periods matter only for financials:
    demonstracoes; maturity only for the [v1.8] options chain/activity/iv
    subtabs; every other adapter ignores them).

    Unknown/malformed keys → 404 PT-BR plain text (never reflected into
    HTML). Registered keys: webui.adapters.registry.adapter_keys().
    """
    if not _ADAPTER_KEY_RE.match(key or "") or not adapter_has(key):
        return PlainTextResponse(
            f"Subtab '{key}' não encontrada.", status_code=404
        )
    data = dispatch(key, ticker.upper(), period=period, periods=periods,
                    maturity=maturity)
    return JSONResponse(data)


@router.get("/macro/sections/{key}")
def macro_sections(key: str):
    """[v1.11] Generic macro subtab endpoint — ticker-less dispatch.

    Same shape as the company /sections/{key} endpoint, minus the ticker:
    macro:* adapters build market-wide payloads (BCB SGS + Focus). Key
    format "macro:<sub>" (overview/juros/inflacao/cambio/atividade/
    retorno_real/focus/curva). Unknown/malformed keys → 404 PT-BR plain
    text (never reflected into HTML).
    """
    if not _ADAPTER_KEY_RE.match(key or "") or not adapter_has(key):
        return PlainTextResponse(
            f"Subtab '{key}' não encontrada.", status_code=404
        )
    data = dispatch(key)
    return JSONResponse(data)


@router.get("/mercado/sections/{key}")
def mercado_sections(key: str):
    """[v1.12] Generic mercado subtab endpoint — ticker-less dispatch.

    Same shape as the macro /sections/{key} endpoint: mercado page
    families build market-wide payloads (DDM — dadosdemercado.com.br).
    Key format "<family>:<sub>" (v1.12: focus:overview/inflacao/
    atividade/juros/cambio/externo/fiscal; v1.13: fluxo:overview/mensal/
    anual/por_investidor; v1.15: inflacao:overview/igpm/ipca/inpc).
    Unknown/malformed keys → 404 PT-BR plain text (never reflected
    into HTML).
    """
    if not _ADAPTER_KEY_RE.match(key or "") or not adapter_has(key):
        return PlainTextResponse(
            f"Subtab '{key}' não encontrada.", status_code=404
        )
    data = dispatch(key)
    return JSONResponse(data)


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


@router.get("/company/{ticker}/proventos-overview")
def company_proventos_overview(ticker: Ticker):
    """[WebUI v1.6] Proventos Visão Geral — KPIs + resumo + charts."""
    data = _proventos_service.overview(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/proventos-historico")
def company_proventos_historico(ticker: Ticker):
    """[WebUI v1.6] Proventos Histórico — complete event list + corporate actions."""
    data = _proventos_service.historico(ticker.upper())
    return JSONResponse(data)


@router.get("/company/{ticker}/proventos-anual")
def company_proventos_anual(ticker: Ticker):
    """[WebUI v1.6] Proventos Anual — per-year aggregation + DVA declarado."""
    data = _proventos_service.anual(ticker.upper())
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
    elif tab == "proventos":
        # [WebUI v1.6] Shell only — subtabs fetch their own JSON endpoints
        # lazily (proventos-overview/-historico/-anual).
        return templates.TemplateResponse(
            request,
            "partials/tab_proventos.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "options":
        # [WebUI v1.8] Shell only — subtabs fetch through the generic
        # /sections/options:<sub> endpoint (overview/chain/activity/iv/
        # positions), chain/activity/iv with a maturity passthrough.
        return templates.TemplateResponse(
            request,
            "partials/tab_options.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "shareholders":
        # [WebUI v1.9] Shell only — subtabs fetch through the generic
        # /sections/shareholders:<sub> endpoint (overview/holders/
        # free_float/equity).
        return templates.TemplateResponse(
            request,
            "partials/tab_shareholders.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "insiders":
        # [WebUI v1.10] Shell only — subtabs fetch through the generic
        # /sections/insiders:<sub> endpoint (overview/transactions/
        # by_role/monthly).
        return templates.TemplateResponse(
            request,
            "partials/tab_insiders.html",
            {"ticker": ticker, "t": tr},
        )
    else:  # financials
        return templates.TemplateResponse(
            request,
            "partials/tab_financials.html",
            {"ticker": ticker, "t": tr},
        )
