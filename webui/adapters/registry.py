"""webui/adapters/registry.py — subtab adapter registry + dispatcher.

[v1.7] One place where every lazy subtab payload producer is registered
under a stable key ``"<family>:<sub>"`` (e.g. ``valuation:overview``,
``proventos:anual``). The generic endpoint
``GET /api/webui/company/{ticker}/sections/{key}`` dispatches through
``dispatch()`` — a new tab in v1.8 (Opções, Histórico, Macro, …) is:

  1. a service method returning a contract payload (see contract.py),
  2. ONE ``register("options:overview", …)`` call in this file,
  3. a tab shell partial + a client loader pointing at /sections/<key>.

No new API route, no api.py edits, no per-endpoint boilerplate.

Design:
  - ``service(cls)`` — memoized singleton factory. The route layer
    (webui/routes/api.py) and this registry share the SAME service
    instances (PriceService carries a 60s-TTL OHLCV cache; duplicating
    instances would duplicate the cache).
  - ``register(key, loader, family, label, generic)`` — loader is a
    zero-arg callable returning the bound service method. The service
    INSTANCE is created lazily on first dispatch, not at import.
  - ``dispatch(key, ticker, **params)`` — runs the adapter inside a
    try/except (exceptions become the canonical error payload — the
    service methods already do this, this is the safety net one level
    up), validates GENERIC payloads against the contract and logs
    violations to stderr with ``_contract_violations`` attached (the
    client ignores unknown keys — contract drift shows in the server
    log during development instead of silently rendering nothing).
  - ``generic=True`` marks payloads drawn by the ONE generic renderer
    (Valuation/Proventos shapes). Custom-renderer payloads (Preço,
    Financeiro, Proventos Histórico) register with ``generic=False``:
    they are dispatched the same way but skip contract validation —
    their shape belongs to their client renderer, not to contract.py.
"""
from __future__ import annotations

import inspect
import re
import sys
import traceback
from typing import Any, Callable

from webui.adapters.contract import error_payload, validate_payload

# NOTE: the service classes are imported INSIDE _register_builtins(), not
# at module level — a service that builds payloads through contract.py
# ("from webui.adapters.contract import …", the documented v1.8 recipe)
# would otherwise create a circular import: registry → service →
# webui.adapters.<contract> → webui.adapters.__init__ → registry (partial).
# Lazy imports keep the v1.7 promise: adding a tab touches only the
# register() block below, and services stay free to use the contract
# builders at module level.

# Bound method produced lazily by a loader — (ticker, **params) -> payload.
AdapterFn = Callable[..., dict[str, Any]]

# key format: "<family>:<sub>" — lowercase letters, digits, _ and -.
_KEY_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_-]+$")


class _Entry:
    __slots__ = ("key", "loader", "fn", "family", "label", "generic",
                 "param_names", "takes_kwargs", "takes_ticker")

    def __init__(self, key: str, loader: Callable[[], AdapterFn],
                 family: str, label: str, generic: bool) -> None:
        self.key = key
        self.loader = loader          # zero-arg → bound method (lazy)
        self.fn: AdapterFn | None = None
        self.family = family
        self.label = label
        self.generic = generic
        # Filled at first bind (see _bind_fn): accepted keyword names +
        # whether the method takes **kwargs.
        self.param_names: frozenset[str] = frozenset()
        self.takes_kwargs = False
        # [v1.11] Ticker-less adapters (macro): bound methods that take NO
        # parameters are called without the positional ticker — macro is
        # market-wide, there is no company to scope the query to.
        self.takes_ticker = True


_REGISTRY: dict[str, _Entry] = {}
_builtins_registered = False


def _ensure_builtins() -> None:
    """Register the built-in adapters on first use (dispatch/has/keys).

    Deliberately lazy: builtin registration imports every service module,
    and services import contract builders from this package — eager
    registration at import time would create a circular import (service →
    webui.adapters.__init__ → registry → service, partially initialized).
    """
    global _builtins_registered
    if _builtins_registered:
        return
    _builtins_registered = True
    _register_builtins()

# ── memoized service singletons (shared with webui/routes/api.py) ──────────
_singletons: dict[type, Any] = {}


def service(cls: type) -> Any:
    """Memoized singleton factory — one instance per service class per
    process, shared by every caller (routes AND adapters)."""
    if cls not in _singletons:
        _singletons[cls] = cls()
    return _singletons[cls]


# ── registry API ─────────────────────────────────────────────────────────────

def register(key: str, loader: Callable[[], AdapterFn], *,
             family: str, label: str, generic: bool = True) -> None:
    """Register a subtab adapter. Idempotent — re-registration overwrites.

    Args:
      key:     "<family>:<sub>" (e.g. "valuation:multiples"). Validated.
      loader:  zero-arg callable returning the bound service method
               (called ONCE on first dispatch, then memoized).
      family:  tab family the key belongs to ("valuation", "proventos", …).
      label:   PT-BR display label (diagnostics / docs).
      generic: True → payload drawn by the generic section renderer and
               validated against contract.py at dispatch time.
    """
    if not _KEY_RE.match(key or ""):
        raise ValueError(f"invalid adapter key: {key!r} "
                         f"(expected '<family>:<sub>')")
    _REGISTRY[key] = _Entry(key, loader, family, label, generic)


def adapter_keys() -> list[str]:
    """All registered keys (sorted)."""
    _ensure_builtins()
    return sorted(_REGISTRY.keys())


def adapters_info() -> list[dict[str, Any]]:
    """Registry snapshot for diagnostics (preflight + docs)."""
    _ensure_builtins()
    return [
        {"key": e.key, "family": e.family, "label": e.label,
         "generic": e.generic}
        for e in sorted(_REGISTRY.values(), key=lambda e: e.key)
    ]


def has(key: str) -> bool:
    _ensure_builtins()
    return key in _REGISTRY


def dispatch(key: str, ticker: str = "", **params: Any) -> dict[str, Any]:
    """Run one adapter for a ticker. Never raises — exceptions become the
    canonical error payload (PT-BR, logged server-side with the traceback).

    Extra ``params`` are forwarded to the adapter ONLY when its method
    signature accepts them (financials:demonstracoes takes period/periods;
    every other adapter takes just the ticker — forwarding would be a
    TypeError, so the rest is filtered out at bind time).

    Generic payloads are contract-validated; violations are logged and
    attached as ``_contract_violations`` (visible in the JSON response,
    ignored by the client renderer).
    """
    entry = _REGISTRY.get(key)
    if entry is None:
        # Late (post-boot) register() calls — check the builtins too.
        _ensure_builtins()
        entry = _REGISTRY.get(key)
    if entry is None:
        return error_payload(ticker, f"subtab desconhecida: {key}")
    tk = (ticker or "").upper()
    try:
        if entry.fn is None:
            _bind_fn(entry)  # lazy bind, memoized
        call_params = ({k: v for k, v in params.items()
                        if entry.takes_kwargs or k in entry.param_names}
                       if params else {})
        # [v1.11] Ticker-less adapters (macro:*) dispatch without the
        # positional ticker — a market-wide query has no company.
        if entry.takes_ticker:
            result = entry.fn(tk, **call_params)
        else:
            result = entry.fn(**call_params)
    except Exception as e:  # noqa: BLE001 — safety net, logged
        print(f"[webui-adapters] dispatch({key}, {tk}) failed: {e}\n"
              f"{traceback.format_exc()}", file=sys.stderr)
        return error_payload(tk, "erro ao carregar dados")

    if not isinstance(result, dict):
        print(f"[webui-adapters] dispatch({key}, {tk}): payload is "
              f"{type(result).__name__}, not dict", file=sys.stderr)
        return error_payload(tk, "resposta inválida do serviço")

    if entry.generic:
        violations = validate_payload(result)
        if violations:
            print(f"[webui-adapters] contract violations in {key} ({tk}): "
                  f"{'; '.join(violations)}", file=sys.stderr)
            result["_contract_violations"] = violations
    return result


# ── builtin registrations (every existing lazy subtab) ─────────────────────
# Loaders create the service instance lazily (first dispatch), then the
# bound method is memoized on the entry.

def _bind_fn(entry: "_Entry") -> None:
    """Bind an entry's loader and introspect the accepted kwargs."""
    fn = entry.loader()
    entry.fn = fn
    try:
        sig = inspect.signature(fn)
        entry.param_names = frozenset(
            p.name for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        )
        entry.takes_kwargs = any(
            p.kind is p.VAR_KEYWORD for p in sig.parameters.values()
        )
        # [v1.11] A bound method with zero parameters (macro adapters) is
        # ticker-less; anything with parameters keeps the (ticker, ...)
        # company contract. VAR_POSITIONAL (*args) also accepts a ticker.
        entry.takes_ticker = bool(sig.parameters) or entry.takes_kwargs or any(
            p.kind is p.VAR_POSITIONAL for p in sig.parameters.values()
        )
    except (TypeError, ValueError):  # builtins/C-callables — ticker only
        entry.param_names = frozenset()
        entry.takes_kwargs = False
        entry.takes_ticker = True


def _bind(cls: type, method: str) -> Callable[[], AdapterFn]:
    return lambda: getattr(service(cls), method)


def _register_builtins() -> None:
    # Lazy service imports (see the NOTE above the class imports at the
    # top of this module — circular-import containment).
    from webui.services.company import CompanyService
    from webui.services.financials import FinancialsService
    from webui.services.insiders import InsiderService
    from webui.services.options import OptionsService
    from webui.services.price import PriceService
    from webui.services.proventos import ProventosService
    from webui.services.shareholders import ShareholdersService
    from webui.services.valuation import ValuationService

    # Valuation — all 5 subtabs render through the generic renderer.
    register("valuation:overview", _bind(ValuationService, "overview"),
             family="valuation", label="Valuation — Visão Geral")
    register("valuation:multiples", _bind(ValuationService, "multiples"),
             family="valuation", label="Valuation — Múltiplos")
    register("valuation:intrinsic", _bind(ValuationService, "intrinsic"),
             family="valuation", label="Valuation — Valor Intrínseco")
    register("valuation:fundamentals", _bind(ValuationService, "fundamentals"),
             family="valuation", label="Valuation — Fundamentos")
    register("valuation:all", _bind(ValuationService, "all_metrics"),
             family="valuation", label="Valuation — Todas as métricas")

    # Proventos — overview/anual are generic; histórico has a custom
    # client renderer (pills, filters, sortable columns).
    register("proventos:overview", _bind(ProventosService, "overview"),
             family="proventos", label="Proventos — Visão Geral")
    register("proventos:historico", _bind(ProventosService, "historico"),
             family="proventos", label="Proventos — Histórico",
             generic=False)
    register("proventos:anual", _bind(ProventosService, "anual"),
             family="proventos", label="Proventos — Anual")

    # Preço — custom client renderers (snapshot tables, indicator charts,
    # Bollinger, volume, Fibonacci). Registered so future tabs/scripts
    # reach them uniformly through the same dispatch path.
    register("preco:cotacao", _bind(PriceService, "price_data"),
             family="preco", label="Preço — Cotação", generic=False)
    register("preco:indicadores", _bind(PriceService, "indicators"),
             family="preco", label="Preço — Indicadores", generic=False)
    register("preco:volatilidade", _bind(PriceService, "volatility"),
             family="preco", label="Preço — Volatilidade", generic=False)
    register("preco:volume", _bind(PriceService, "volume"),
             family="preco", label="Preço — Volume", generic=False)
    register("preco:fibonacci", _bind(PriceService, "fibonacci"),
             family="preco", label="Preço — Fibonacci", generic=False)

    # Financeiro — custom client renderers. demonstracoes accepts
    # period/periods passthrough params from the generic endpoint.
    register("financials:overview", _bind(FinancialsService, "overview"),
             family="financials", label="Financeiro — Visão Geral",
             generic=False)
    register("financials:demonstracoes",
             _bind(FinancialsService, "statements"),
             family="financials", label="Financeiro — Demonstrações",
             generic=False)

    # [v1.8] Opções — the reorganized options dashboard (reference:
    # skills/b3/options static report + PETR4_options_dashboard.html).
    # chain/activity/iv accept a maturity passthrough param (the pill bar
    # refetches /sections/<key>?maturity=YYYY-MM-DD).
    register("options:overview", _bind(OptionsService, "overview"),
             family="options", label="Opções — Visão Geral")
    register("options:chain", _bind(OptionsService, "chain"),
             family="options", label="Opções — Cadeia")
    register("options:activity", _bind(OptionsService, "activity"),
             family="options", label="Opções — Volume & Exercícios")
    register("options:iv", _bind(OptionsService, "iv"),
             family="options", label="Opções — Vol. Implícita")
    register("options:positions", _bind(OptionsService, "positions"),
             family="options", label="Opções — Posições")

    # [v1.9] Acionistas — the reorganized shareholders dashboard (reference:
    # skills/cvm/shareholders static report + PETR4_shareholders_dashboard
    # .html). All four subtabs are FLAT payloads → generic renderer.
    register("shareholders:overview", _bind(ShareholdersService, "overview"),
             family="shareholders", label="Acionistas — Visão Geral")
    register("shareholders:holders", _bind(ShareholdersService, "holders"),
             family="shareholders", label="Acionistas — Posição Acionária")
    register("shareholders:free_float",
             _bind(ShareholdersService, "free_float"),
             family="shareholders", label="Acionistas — Free Float")
    register("shareholders:equity", _bind(ShareholdersService, "equity"),
             family="shareholders", label="Acionistas — Estrutura Patrimonial")

    # [v1.10] Insiders — the reorganized insider-trading dashboard
    # (reference: skills/cvm/insider static report +
    # PETR4_insider_dashboard.html). All four subtabs are FLAT payloads
    # → generic renderer. Data: VLMO (vlmo.db) through the same query
    # engine the skill's modes use (with the compra*/venda* prefix fix).
    register("insiders:overview", _bind(InsiderService, "overview"),
             family="insiders", label="Insiders — Visão Geral")
    register("insiders:transactions",
             _bind(InsiderService, "transactions"),
             family="insiders", label="Insiders — Movimentações")
    register("insiders:by_role", _bind(InsiderService, "by_role"),
             family="insiders", label="Insiders — Por Cargo")
    register("insiders:monthly", _bind(InsiderService, "monthly"),
             family="insiders", label="Insiders — Mensal")

    # [v1.11] Macro — the /webui/macro page (reference: skills/bcb/macro
    # static report + macro_dashboard.html). Ticker-less FLAT payloads
    # (market-wide — no company scope) served by the dedicated
    # GET /api/webui/macro/sections/{key} endpoint. Data: BCB SGS
    # (sgs.db) + BCB Focus (focus.db) through the same query engines the
    # skill's modes use.
    from webui.services.macro import MacroService
    register("macro:overview", _bind(MacroService, "overview"),
             family="macro", label="Macro — Visão Geral")
    register("macro:juros", _bind(MacroService, "juros"),
             family="macro", label="Macro — Juros")
    register("macro:inflacao", _bind(MacroService, "inflacao"),
             family="macro", label="Macro — Inflação")
    register("macro:cambio", _bind(MacroService, "cambio"),
             family="macro", label="Macro — Câmbio")
    register("macro:atividade", _bind(MacroService, "atividade"),
             family="macro", label="Macro — Atividade")
    register("macro:retorno_real", _bind(MacroService, "retorno_real"),
             family="macro", label="Macro — Retorno Real")
    register("macro:focus", _bind(MacroService, "focus"),
             family="macro", label="Macro — Expectativas Focus")
    register("macro:curva", _bind(MacroService, "curva"),
             family="macro", label="Macro — Curva de Juros")

    # [v1.12] Mercado — the /webui/mercado page, the new home for the
    # DDM dashboards (reference: skills/ddm/focus static report +
    # focus_dashboard.html; market-level data from dadosdemercado.com.br).
    # Focus family first (Boletim Focus — the weekly expectations
    # bulletin, 3 time windows × 4 reference years); índices (v1.14),
    # fluxo (v1.13), inflação (v1.15) and juros (v1.16) joined as later
    # families; dividends is the remaining one. Ticker-less FLAT
    # payloads served by the dedicated GET /api/webui/macro-style
    # endpoint /api/webui/mercado/sections/{key}. Data: DDM focus.db
    # through the same query engine the skill's modes use.
    from webui.services.focus import FocusService
    register("focus:overview", _bind(FocusService, "overview"),
             family="focus", label="Mercado — Focus: Visão Geral")
    register("focus:inflacao", _bind(FocusService, "inflacao"),
             family="focus", label="Mercado — Focus: Inflação")
    register("focus:atividade", _bind(FocusService, "atividade"),
             family="focus", label="Mercado — Focus: Atividade")
    register("focus:juros", _bind(FocusService, "juros"),
             family="focus", label="Mercado — Focus: Juros")
    register("focus:cambio", _bind(FocusService, "cambio"),
             family="focus", label="Mercado — Focus: Câmbio")
    register("focus:externo", _bind(FocusService, "externo"),
             family="focus", label="Mercado — Focus: Setor Externo")
    register("focus:fiscal", _bind(FocusService, "fiscal"),
             family="focus", label="Mercado — Focus: Fiscal")

    # [v1.13] Mercado — Fluxo family (the B3 investment flow by investor
    # type, also from dadosdemercado.com.br; reference:
    # skills/ddm/fluxo static report + fluxo_dashboard.html). The static's
    # 5 flat tabs (1 Fluxo + 4 per-investor × Diário/Mensal/Anual) become
    # 4 comparison-driven subtabs over the same fluxo.db query engine.
    # Ticker-less FLAT payloads served by the same
    # GET /api/webui/mercado/sections/{key} endpoint as the focus family.
    from webui.services.fluxo import FluxoService
    register("fluxo:overview", _bind(FluxoService, "overview"),
             family="fluxo", label="Mercado — Fluxo: Visão Geral")
    register("fluxo:mensal", _bind(FluxoService, "mensal"),
             family="fluxo", label="Mercado — Fluxo: Mensal")
    register("fluxo:anual", _bind(FluxoService, "anual"),
             family="fluxo", label="Mercado — Fluxo: Anual")
    register("fluxo:por_investidor",
             _bind(FluxoService, "por_investidor"),
             family="fluxo", label="Mercado — Fluxo: Por Investidor")

    # [v1.14] Mercado — Índices family (B3 index compositions from the
    # indexProxy API; reference: skills/b3/index static report +
    # index_dashboard.html). The static's 6 flat tabs (Resumo + 5
    # per-index tabs, chart capped at the top 15 and table at 20) become
    # 6 subtabs: the overview gains the cross-index presence view and
    # each index gets the FULL doughnut + the complete table. Ticker-less
    # FLAT payloads served by the same
    # GET /api/webui/mercado/sections/{key} endpoint as the other
    # families. Data: b3 index.db through the same query engine the
    # skill's modes use.
    from webui.services.indexes import IndexesService
    register("indices:overview", _bind(IndexesService, "overview"),
             family="indices", label="Mercado — Índices: Visão Geral")
    register("indices:ibov", _bind(IndexesService, "ibov"),
             family="indices", label="Mercado — Índices: IBOV")
    register("indices:smll", _bind(IndexesService, "smll"),
             family="indices", label="Mercado — Índices: SMLL")
    register("indices:bdrx", _bind(IndexesService, "bdrx"),
             family="indices", label="Mercado — Índices: BDRX")
    register("indices:ifix", _bind(IndexesService, "ifix"),
             family="indices", label="Mercado — Índices: IFIX")
    register("indices:idiv", _bind(IndexesService, "idiv"),
             family="indices", label="Mercado — Índices: IDIV")

    # [v1.15] Mercado — Inflação family (the Brazilian price indices from
    # dadosdemercado.com.br; reference: skills/ddm/inflation static
    # report + inflation_dashboard.html). The static's 4 flat tabs (IGP-M,
    # IPCA and INPC each with Histórico + Matriz subtabs, plus a
    # Comparativo tab) become 4 subtabs: the comparison lands on the
    # overview (the static's 12m overlay was the LAST tab) and each
    # index's Histórico + Matriz merge into ONE subtab. Ticker-less FLAT
    # payloads served by the same GET /api/webui/mercado/sections/{key}
    # endpoint as the other families. Data: ddm inflation.db through the
    # same query engine the skill's modes use.
    from webui.services.inflation import InflationService
    register("inflacao:overview", _bind(InflationService, "overview"),
             family="inflacao", label="Mercado — Inflação: Visão Geral")
    register("inflacao:igpm", _bind(InflationService, "igpm"),
             family="inflacao", label="Mercado — Inflação: IGP-M")
    register("inflacao:ipca", _bind(InflationService, "ipca"),
             family="inflacao", label="Mercado — Inflação: IPCA")
    register("inflacao:inpc", _bind(InflationService, "inpc"),
             family="inflacao", label="Mercado — Inflação: INPC")

    # [v1.16] Mercado — Juros family (the Brazilian interest rates from
    # dadosdemercado.com.br; reference: skills/ddm/juros static report +
    # juros_dashboard.html). The static's 4 flat tabs (Selic, Meta Selic
    # and CDI each with Histórico + Matriz subtabs, plus a Comparativo
    # tab) become 4 subtabs: the comparison lands on the overview (the
    # static's overlay was the LAST tab) and each rate's Histórico +
    # Matriz merge into ONE subtab. Ticker-less FLAT payloads served by
    # the same GET /api/webui/mercado/sections/{key} endpoint as the
    # other families. Data: ddm juros.db through the same query engine
    # the skill's modes use.
    from webui.services.juros import JurosService
    register("juros:overview", _bind(JurosService, "overview"),
             family="juros", label="Mercado — Juros: Visão Geral")
    register("juros:selic", _bind(JurosService, "selic"),
             family="juros", label="Mercado — Juros: Selic")
    register("juros:meta_selic", _bind(JurosService, "meta_selic"),
             family="juros", label="Mercado — Juros: Meta Selic")
    register("juros:cdi", _bind(JurosService, "cdi"),
             family="juros", label="Mercado — Juros: CDI")
