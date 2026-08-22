"""data_sources/ddm/fluxo/__init__.py -- Fluxo sub-domain manifest + router.

DDM Fluxo = Brazilian B3 investment flow (daily net inflow / outflow by
investor type) scraped from dadosdemercado.com.br/fluxo. The page exposes
1 table: `<table class="normal-table">` with 6 columns:

    Data | Estrangeiro | Institucional | Pessoa fisica |
    Inst. Financeira | Outros

~247 data rows (daily data, ~1 year of trading days). Dates are DD/MM/YYYY
DESC (newest first). Values are PT-BR formatted strings with the "mi"
suffix (millions of R$):
    "-1.582,35 mi"   = -1582.35 million R$ (outflow)
    "1.029,81 mi"    = 1029.81 million R$ (inflow)
    "42,36 mi"       = 42.36 million R$

8 modes: sync_all, sync_index, fluxo_data, last, search, summary, status,
ticker.

Data source: www.dadosdemercado.com.br/fluxo (HTML scrape,
CloudFront-protected - fetcher sends full Chrome 127 browser headers)
Storage:     memory_db/ddm/fluxo.db

The route() dispatcher follows the ddm/focus pattern: lazy-imports each
mode's module on first dispatch, filters kwargs by the target function's
signature, and returns a structured dict (status / error / traceback on
failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "fluxo",
    "description": (
        "DDM Fluxo - Brazilian B3 investment flow (daily net inflow / "
        "outflow by investor type) scraped from dadosdemercado.com.br/fluxo. "
        "1 table with 6 columns: Data | Estrangeiro | Institucional | "
        "Pessoa fisica | Inst. Financeira | Outros. ~247 data rows "
        "(daily data, ~1 year). Values stored as REAL (millions of R$); "
        "PT-BR parsed at the fetcher boundary ('-1.582,35 mi' -> "
        "-1582.35). Dates stored as YYYY-MM-DD. CloudFront-protected - "
        "fetcher sends full Chrome 127 browser headers. Thread-safe "
        "cache (5-min TTL, Semaphore(5))."
    ),
    "source":  "www.dadosdemercado.com.br/fluxo (HTML scrape, browser headers)",
    "storage": "memory_db/ddm/fluxo.db",
    "modes": {
        "sync_all": {
            "description": (
                "Fetch + parse + store the /fluxo page (single HTTP "
                "call). Idempotent via INSERT OR REPLACE on ref_date."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": "Alias for sync_all (the fluxo page is single-page, not per-index).",
            "include_in_all": True,
            "params": {
                "slug":  "str. Ignored (kept for API parity). Default: 'fluxo'.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="sync_index")',
            ],
        },
        "fluxo_data": {
            "description": "Get all observations (daily data, ascending by date).",
            "include_in_all": True,
            "params": {
                "limit": "int. Max results. Default: 0 (all).",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="fluxo_data")',
            ],
        },
        "last": {
            "description": "Get the latest observation (most recent ref_date).",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="last")',
            ],
        },
        "search": {
            "description": "Search observations by date (YYYY-MM-DD prefix match).",
            "include_in_all": False,
            "params": {
                "query": "str. Date fragment (e.g. '2026-08'). Required.",
                "limit": "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="search", '
                'params=\'{"query":"2026-08"}\')',
            ],
        },
        "summary": {
            "description": "Overview stats: row count, date range, last sync.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="summary")',
            ],
        },
        "status": {
            "description": "Show fluxo.db stats: row count + date range + last sync.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="status")',
            ],
        },
        "ticker": {
            "description": "Get one observation by date (YYYY-MM-DD or DD/MM/YYYY).",
            "include_in_all": True,
            "params": {
                "ticker": "str. Date (YYYY-MM-DD or DD/MM/YYYY). Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="fluxo", mode="ticker", '
                'params=\'{"ticker":"2026-08-19"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch fluxo mode call (sgs pattern: lazy-import + filter kwargs)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_all":
            from data_sources.ddm.fluxo.sync_engine import sync_all as _fn
        elif mode == "sync_index":
            from data_sources.ddm.fluxo.sync_engine import sync_index as _fn
        elif mode == "fluxo_data":
            from data_sources.ddm.fluxo.query_engine import fluxo_data as _fn
        elif mode == "last":
            from data_sources.ddm.fluxo.query_engine import last_value as _fn
        elif mode == "search":
            from data_sources.ddm.fluxo.query_engine import search as _fn
        elif mode == "summary":
            from data_sources.ddm.fluxo.query_engine import summary as _fn
        elif mode == "status":
            from data_sources.ddm.fluxo.status_reporter import status as _fn
        elif mode == "ticker":
            from data_sources.ddm.fluxo.query_engine import by_date as _fn
        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

        sig = inspect.signature(_fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return _fn(**filtered)

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "fluxo",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
