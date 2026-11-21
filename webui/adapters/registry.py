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
from webui.services.company import CompanyService
from webui.services.financials import FinancialsService
from webui.services.price import PriceService
from webui.services.proventos import ProventosService
from webui.services.valuation import ValuationService

# Bound method produced lazily by a loader — (ticker, **params) -> payload.
AdapterFn = Callable[..., dict[str, Any]]

# key format: "<family>:<sub>" — lowercase letters, digits, _ and -.
_KEY_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_-]+$")


class _Entry:
    __slots__ = ("key", "loader", "fn", "family", "label", "generic",
                 "param_names", "takes_kwargs")

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


_REGISTRY: dict[str, _Entry] = {}

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
    return sorted(_REGISTRY.keys())


def adapters_info() -> list[dict[str, Any]]:
    """Registry snapshot for diagnostics (preflight + docs)."""
    return [
        {"key": e.key, "family": e.family, "label": e.label,
         "generic": e.generic}
        for e in sorted(_REGISTRY.values(), key=lambda e: e.key)
    ]


def has(key: str) -> bool:
    return key in _REGISTRY


def dispatch(key: str, ticker: str, **params: Any) -> dict[str, Any]:
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
        return error_payload(ticker, f"subtab desconhecida: {key}")
    tk = (ticker or "").upper()
    try:
        if entry.fn is None:
            _bind_fn(entry)  # lazy bind, memoized
        call_params = ({k: v for k, v in params.items()
                        if entry.takes_kwargs or k in entry.param_names}
                       if params else {})
        result = entry.fn(tk, **call_params)
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
    except (TypeError, ValueError):  # builtins/C-callables — ticker only
        entry.param_names = frozenset()
        entry.takes_kwargs = False


def _bind(cls: type, method: str) -> Callable[[], AdapterFn]:
    return lambda: getattr(service(cls), method)


def _register_builtins() -> None:
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


_register_builtins()
