"""data_sources/ddm/focus/__init__.py -- Focus sub-domain manifest + router.

DDM Focus = Brazilian Boletim Focus (market expectations survey) scraped
from dadosdemercado.com.br/boletim-focus. The page exposes 4 yearly tables
(2026, 2027, 2028, 2029), each `<table class="normal-table">` with 6
columns: Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.

12-13 indicator rows per year: IPCA, PIB Total, Cambio, Selic, IGP-M,
IPCA Adm, Conta corrente, Balanca comercial, Investimento direto no pais,
Divida liquida setor pub, Resultado primario, Resultado nominal.

8 modes: sync_all, sync_index, focus_data, last, search, summary, status,
indicator.

Data source: www.dadosdemercado.com.br/boletim-focus (HTML scrape,
CloudFront-protected - fetcher sends full browser headers)
Storage:     memory_db/ddm/focus.db

The route() dispatcher follows the ddm/acoes pattern: lazy-imports each
mode's module on first dispatch, filters kwargs by the target function's
signature, and returns a structured dict (status / error / traceback on
failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations

from data_sources.ddm._base.route_base import make_ddm_route

MANIFEST = {
    "sub_domain":  "focus",
    "description": (
        "DDM Focus - Brazilian Boletim Focus (market expectations survey) "
        "scraped from dadosdemercado.com.br/boletim-focus. The page exposes "
        "4 yearly tables (2026, 2027, 2028, 2029), each with 6 columns: "
        "Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp. Values "
        "preserved as PT-BR strings ('5,151%', 'R$ 5,200'). CloudFront-"
        "protected - fetcher sends full Chrome 127 browser headers. "
        "Thread-safe cache (5-min TTL, Semaphore(5))."
    ),
    "source":  "www.dadosdemercado.com.br/boletim-focus (HTML scrape, browser headers)",
    "storage": "memory_db/ddm/focus.db",
    "modes": {
        "sync_all": {
            "description": (
                "Fetch + parse + store the boletim-focus page (single HTTP "
                "call). Idempotent via INSERT OR REPLACE on "
                "(year, indicator, ref_date)."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": "Alias for sync_all (the focus page is single-page, not per-index).",
            "include_in_all": True,
            "params": {
                "slug":  "str. Ignored (kept for API parity). Default: 'focus'.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="sync_index")',
            ],
        },
        "focus_data": {
            "description": "Get all observations for the latest sync (full snapshot).",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="focus_data")',
            ],
        },
        "last": {
            "description": "Get the latest sync metadata + all observations.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="last")',
            ],
        },
        "search": {
            "description": "Search observations by indicator name (case-insensitive LIKE).",
            "include_in_all": False,
            "params": {
                "query": "str. Indicator name fragment. Required.",
                "limit": "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="search", '
                'params=\'{"query":"IPCA"}\')',
            ],
        },
        "summary": {
            "description": "Overview stats: years, indicators, last sync.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="summary")',
            ],
        },
        "status": {
            "description": "Show focus.db stats: row count + year/indicator counts + last sync.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="status")',
            ],
        },
        "indicator": {
            "description": "Get all years for a given indicator (latest sync only).",
            "include_in_all": True,
            "params": {
                "indicator": "str. Indicator name (e.g. 'IPCA'). Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="focus", mode="indicator", '
                'params=\'{"indicator":"Selic"}\')',
            ],
        },
    },
}


# mode -> (module_path, function_name) lazy-import map.
_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.focus.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.focus.sync_engine",     "sync_all"),
    "focus_data": ("data_sources.ddm.focus.query_engine",    "all_data"),
    "last":       ("data_sources.ddm.focus.query_engine",    "last_value"),
    "search":     ("data_sources.ddm.focus.query_engine",    "search"),
    "summary":    ("data_sources.ddm.focus.query_engine",    "summary"),
    "indicator":  ("data_sources.ddm.focus.query_engine",    "focus_by_indicator"),
    "status":     ("data_sources.ddm.focus.status_reporter", "status"),
}

route = make_ddm_route(
    sub_domain="focus",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
