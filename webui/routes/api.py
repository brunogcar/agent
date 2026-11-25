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
[v1.17] acoes:* joins the mercado endpoint (2 subtabs — the DDM
  listed-stocks family: overview + evolucao — the distribution over
  time fed by the stocks_history snapshots accumulated per sync).
[v1.18] dividendos:* joins the mercado endpoint (4 subtabs — the DDM
  Proventos family: overview (B3 natives) + bdrs (the *34 split) +
  empresas (per-ticker aggregation) + calendario (per-day payments,
  pago vs a pagar)). The family DISPLAY name is "Proventos"; the key
  names the data source (the company page owns proventos:*).
[v1.19] GET /api/webui/home — the Painel landing payload (BCB SGS KPI
  row + 5 ranked ticker cards over b3-index + cotahist; see
  webui/services/home.py). The dashboard's sync ribbon is GONE from
  the top — the page bottom now carries the compact /api/webui/sync/box
  (routes/sync.py) and the full table stays on the Sincronização page.

Routes:
  GET /api/webui/home                       → Painel landing payload (KPI row
        + 5 ticker cards) [v1.19]
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
        igpm/ipca/inpc; juros: overview/selic/meta_selic/cdi; acoes:
        overview/evolucao; dividendos: overview/bdrs/empresas/
        calendario)
        [v1.12, v1.13, v1.14, v1.15, v1.16, v1.17, v1.18]
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
  GET /api/webui/company/{ticker}/backtest/meta         → Backtest form catalog (JSON) [v1.25]
  POST /api/webui/company/{ticker}/backtest/run         → run ONE parametrized scenario (JSON) [v1.25]
  GET /api/webui/company/{ticker}/governance/practices  → CGVN práticas + filtros (JSON) [v1.26]
  GET /api/webui/company/{ticker}/ipe/events           → IPE eventos facetados (JSON) [v1.26 fix 1 — its own tab]
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
from webui.services.home import HomeService
from webui.services.price import PriceService
from webui.services.financials import FinancialsService
from webui.services.valuation import ValuationService
from webui.services.proventos import ProventosService
from webui.services.backtest import BacktestService
from webui.services.governance import GovernanceService
from webui.services.ipe import IpeService
from webui.services.comparison import ComparisonService
from webui.templating import templates
# [v1.22] ONE ticker definition (webui/validators.py).
from webui.validators import TICKER_PATTERN

router = APIRouter(prefix="/api/webui", tags=["webui-api"])

# [v1.7] Singletons via the adapters registry factory — the generic
# /sections/{key} dispatch path binds the SAME instances (one PriceService
# = one shared OHLCV cache, as intended since v1.5).
def _svc(cls):
    from webui.adapters.registry import service
    return service(cls)


_company_service = _svc(CompanyService)
_home_service = _svc(HomeService)
_price_service = _svc(PriceService)
_financials_service = _svc(FinancialsService)
_valuation_service = _svc(ValuationService)
_proventos_service = _svc(ProventosService)
_backtest_service = _svc(BacktestService)
_governance_service = _svc(GovernanceService)
_ipe_service = _svc(IpeService)
_comparison_service = _svc(ComparisonService)

# ── [WebUI v1.5] Ticker validation ──────────────────────────────────────────
# B3 symbols: letter + 3-5 alphanumerics + 1-2 digits + optional
# trailing letter (PETR4, BOVA11, UNIT11, AAPL34, B3SA3, A1MD34, …).
# [v1.22] The old letters-only stem rejected B3's own ticker (B3SA3)
# and BDRs — a digit in the stem is legal B3 symbology. Validated at
# the route boundary so garbage never reaches the engines, SQL LIKE
# patterns, Jinja contexts or client JS strings. FastAPI returns 422
# automatically on mismatch.
Ticker = Annotated[str, Path(pattern=TICKER_PATTERN)]

# [v1.7] Adapter key validation — "<family>:<sub>" (colon is a legal path
# character, RFC 3986). Checked BEFORE dispatch; unknown keys get a 404
# PT-BR plain-text message (same pattern as the tab route — never reflect
# the raw param into HTML).
_ADAPTER_KEY_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_-]+$")

# Tabs with a rendered partial (historical is future work —
# company.html hides its button until it exists). [v1.6] proventos.
# [v1.8] options. [v1.9] shareholders. [v1.10] insiders.
# [v1.24] historical SHIPS (the 4-subtab Histórico tab).
# [v1.25] backtest (the interactive simulator tab).
# [v1.26] governance (Governança — CGVN only) + ipe (Informações
# Periódicas — the IPE event index, SPLIT into its own tab in
# v1.26 fix 1: "both provide info, but they are not supposed to be
# together, different purpose").
_ALLOWED_TABS = {"visao_geral", "valuation", "preco", "financials", "historical", "proventos", "options", "shareholders", "insiders", "governance", "ipe", "backtest"}

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


@router.get("/home")
def home_overview():
    """[v1.19] Painel landing page — one payload, one screen.

    Macro KPI row (Selic anualizada, IPCA/IGP-M acumulado 12m, USD/BRL
    ptax — BCB SGS) + 5 ranked ticker cards (Top 10 IBOV / SMLL by weight
    with quote enrichment; Mais Negócios / Maiores Altas / Maiores Baixas
    from the latest cotahist session). Section-scoped degradation: each
    part fails alone with a PT-BR message naming its sync source.
    Rendered by loadHomeData() in app.js.
    """
    return JSONResponse(_home_service.overview())


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


@router.get("/tools/comparison")
def tools_comparison(tickers: str = Query("")):
    """[v1.27] Comparação — the first Ferramentas tool.

    The online-shop side-by-side: one column per company (2-4), metric
    rows grouped by theme (Mercado/Valuation/Rentabilidade/Crescimento/
    Dividendos/Endividamento/Demonstrativos), the BEST value per row
    ranked server-side, leader KPI cards, a normalized radar + grouped
    bars and the raw 5Y month-end closes for the client-side base-100
    performance chart. Payload-cached on the composite fingerprint of
    every compared ticker (the v1.26.1 webui_payloads foundation).
    Validation errors (fewer than 2, more than 4, bad ticker shape)
    return the canonical {"status": "error", "error": …} payload.
    """
    return JSONResponse(_comparison_service.compare(tickers))


@router.get("/tools/comparison/search")
def tools_comparison_search(q: str = Query("")):
    """[v1.27] JSON ticker search for the comparison picker.

    Same bridge-DB search as the top bar's HTMX /search, but JSON (the
    picker renders its own dropdown; the top bar keeps its HTML
    fragment).
    """
    return JSONResponse({"results": _company_service.search(q, limit=8)})


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


# ── [v1.25] Backtest — the interactive simulator ─────────────────────────

@router.get("/company/{ticker}/backtest/meta")
def company_backtest_meta(ticker: Ticker):
    """[v1.25] The Backtest form catalog — strategies (with their
    parametrizable entry/exit conditions), the ticker's price range and
    the engine defaults. One fetch primes the whole form."""
    data = _backtest_service.meta(ticker.upper())
    return JSONResponse(data)


@router.post("/company/{ticker}/backtest/run")
async def company_backtest_run(request: Request, ticker: Ticker):
    """[v1.25] Run ONE parametrized scenario → full interactive payload
    (KPIs, equity × buy&hold, drawdown, price-with-markers, trade log).

    The body MUST be application/json (the v1.22 CSRF rule — a
    cross-site text/plain POST must not parse). The handler stays async
    only to await the body; the engine (SQLite scans + the signal
    precompute) runs via run_in_threadpool so the event loop never
    blocks on a 10-year backtest.
    """
    from starlette.concurrency import run_in_threadpool
    if "application/json" not in (request.headers.get("content-type")
                                   or "").lower():
        return JSONResponse({"_error": "Corpo inválido — esperado um objeto JSON."},
                            status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"_error": "Corpo inválido — esperado um objeto JSON."},
                            status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"_error": "Corpo inválido — esperado um objeto JSON."},
                            status_code=400)
    data = await run_in_threadpool(_backtest_service.run, ticker.upper(), body)
    status = 400 if (data.get("_error") and data.get("status") != "ok") else 200
    return JSONResponse(data, status_code=status)


# ── [v1.26] Governança (CGVN) + Informações Periódicas (IPE, its own tab since v1.26 fix 1) ───────────────────────

@router.get("/company/{ticker}/governance/practices")
def company_governance_practices(
    ticker: Ticker,
    data_ref: str = Query(""),
    capitulo: str = Query(""),
    adotada: str = Query(""),
    q: str = Query(""),
):
    """[v1.26] The Práticas subtab (Governança tab) — the CGVN
    54-practice table for ONE filing (data_ref; default = latest) with
    server-side Capítulo/Situação/busca filters, plus the filings list
    for the Exercício select. The Visão Geral subtab goes through the
    generic /sections/governance:overview endpoint (registry)."""
    data = _governance_service.practices(
        ticker.upper(), data_ref=data_ref, capitulo=capitulo,
        adotada=adotada, q=q)
    return JSONResponse(data)


@router.get("/company/{ticker}/ipe/events")
def company_ipe_events(
    ticker: Ticker,
    categoria: str = Query(""),
    tipo: str = Query(""),
    especie: str = Query(""),
    ano: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """[v1.26 fix 1] The Informações Periódicas tab — ONE faceted page
    of the ticker's IPE events (moved from /governance/events when the
    tab was SPLIT: CGVN = self-assessment, IPE = filed events —
    different purposes). Exact-match categoria/tipo/especie (the
    sentinel __none__ selects the empty value), ano, keyword,
    pagination; the response carries the four cascading facet lists
    (each respects every filter except its own field; anos
    CHRONOLOGICAL, newest first — the count-ordered select the user
    reported, fixed)."""
    data = _ipe_service.events(
        ticker.upper(), categoria=categoria, tipo=tipo, especie=especie,
        ano=ano, q=q, page=page, per_page=per_page)
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
    elif tab == "historical":
        # [v1.24] Shell only — subtabs fetch through the generic
        # /sections/historical:<sub> endpoint (overview/valuation/
        # profitability/leverage — the 9 static-dashboard tabs
        # reshaped into 4, charts side by side).
        return templates.TemplateResponse(
            request,
            "partials/tab_historical.html",
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
    elif tab == "governance":
        # [v1.26] Governança — CGVN only (Código de Melhores Práticas:
        # score/práticas/evolução). Visão Geral loads through the generic
        # /sections/governance:overview endpoint; Práticas has its
        # dedicated endpoint (filters are interactive state — the
        # proventos:historico precedent).
        return templates.TemplateResponse(
            request,
            "partials/tab_governance.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "ipe":
        # [v1.26 fix 1] Informações Periódicas — the IPE event index in
        # its OWN tab (split from Governança: different purpose — what
        # the company FILED, not how it self-assesses). No subtabs: the
        # faceted explorer pane boots on afterSettle (initIpeTab).
        return templates.TemplateResponse(
            request,
            "partials/tab_ipe.html",
            {"ticker": ticker, "t": tr},
        )
    elif tab == "backtest":
        # [v1.25] The interactive simulator shell — the form, the result
        # area and the scenario manager. The client fetches /backtest/meta
        # (form catalog) on load and POSTs /backtest/run per simulation.
        return templates.TemplateResponse(
            request,
            "partials/tab_backtest.html",
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
