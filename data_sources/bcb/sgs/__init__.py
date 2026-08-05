"""data_sources/bcb/sgs/__init__.py -- SGS sub-domain manifest and router.

BCB SGS = Sistema Gerenciador de Series Temporais (Brazilian Central Bank
Time Series Manager). Public, free, no auth.

12 curated series cover the 4 macro categories:
  - Juros     : Selic diaria, CDI diaria, TR, Meta Copom, Selic acumulada (x2)
  - Inflacao  : IPCA mensal, IGP-M mensal
  - Cambio    : USD/BRL ptax venda, USD/BRL ptax mensal
  - Atividade : PIB nominal trimestral, Salario minimo mensal

8 modes: sync_all, sync_series, sync_series_range, series, last, search,
summary, status.

Data source: api.bcb.gov.br (live REST API, no auth)
Storage:     memory_db/bcb/sgs.db

The route() dispatcher follows the CVM itr pattern: lazy-imports each mode's
module on first dispatch, filters kwargs by the target function's signature,
and returns a structured dict (status / error / traceback on failure).
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "sgs",
    "description": (
        "BCB SGS (Sistema Gerenciador de Series Temporais) - 12 curated "
        "macro series (Selic, CDI, TR, IPCA, IGP-M, USD/BRL, PIB, etc.). "
        "Public API, no auth. Thread-safe concurrent fetcher (Semaphore(5)). "
        "4 categories: Juros, Inflacao, Cambio, Atividade."
    ),
    "source":  "api.bcb.gov.br (live REST API, no auth)",
    "storage": "memory_db/bcb/sgs.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync every series in SERIES_CATALOG concurrently "
                "(Semaphore(5), ~12 HTTP calls). Idempotent via INSERT OR REPLACE."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="sync_all")',
            ],
        },
        "sync_series": {
            "description": "Sync one series (full available history). Idempotent.",
            "include_in_all": True,
            "params": {
                "code":  "int. BCB SGS series code (e.g. 11 = Selic). Required.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="sync_series", params=\'{"code":11}\')',
            ],
        },
        "sync_series_range": {
            "description": "Sync one series for a specific date window [start, end].",
            "include_in_all": False,
            "params": {
                "code":  "int. Required.",
                "start": "str. YYYY-MM-DD. Required.",
                "end":   "str. YYYY-MM-DD. Required.",
                "force": "bool. Default: false.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="sync_series_range", params=\'{"code":11,"start":"2024-01-01","end":"2024-12-31"}\')',
            ],
        },
        "series": {
            "description": "Query observations for a series (most-recent N or windowed).",
            "include_in_all": True,
            "params": {
                "code":  "int. Required.",
                "days":  "int. Number of most-recent obs. Default: 30.",
                "start": "str. YYYY-MM-DD. Optional window start.",
                "end":   "str. YYYY-MM-DD. Optional window end.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="series", params=\'{"code":11,"days":90}\')',
            ],
        },
        "last": {
            "description": "Get the most recent observation for a series.",
            "include_in_all": True,
            "params": {
                "code": "int. Required.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="last", params=\'{"code":11}\')',
            ],
        },
        "search": {
            "description": "Search series catalog by name fragment (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="search", params=\'{"query":"Selic"}\')',
            ],
        },
        "summary": {
            "description": "Catalog overview: every series sorted by (category, code).",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="summary")',
            ],
        },
        "status": {
            "description": "Show sgs.db stats: per-series row counts + last sync timestamps.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="bcb", sub_domain="sgs", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch sgs mode call (CVM itr pattern: lazy-import + filter kwargs)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_all":
            from data_sources.bcb.sgs.sync_engine import sync_all as _fn
        elif mode == "sync_series":
            from data_sources.bcb.sgs.sync_engine import sync_series as _fn
        elif mode == "sync_series_range":
            from data_sources.bcb.sgs.sync_engine import sync_series_range as _fn
        elif mode == "series":
            from data_sources.bcb.sgs.query_engine import series as _fn
        elif mode == "last":
            from data_sources.bcb.sgs.query_engine import last_value as _fn
        elif mode == "search":
            from data_sources.bcb.sgs.query_engine import search as _fn
        elif mode == "summary":
            from data_sources.bcb.sgs.query_engine import summary as _fn
        elif mode == "status":
            from data_sources.bcb.sgs.status_reporter import status as _fn
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
            "sub_domain": "sgs",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
