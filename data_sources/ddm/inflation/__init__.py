"""data_sources/ddm/inflation/__init__.py -- Inflation sub-domain manifest + router.

DDM Inflation = Brazilian inflation indices scraped from dadosdemercado.com.br.
Each index has its own page with 2 HTML tables (monthly matrix + historical
monthly series). Server-rendered HTML, no JS, no auth.

3 curated indices:
  - IGP-M (Indice Geral de Precos - Mercado)
  - IPCA  (Indice Nacional de Precos ao Consumidor Amplo)
  - INPC  (Indice Nacional de Precos ao Consumidor)

8 modes: sync_all, sync_index, series, last, matrix, search, summary, status.

Data source: www.dadosdemercado.com.br/indices/{slug} (HTML scrape)
Storage:     memory_db/ddm/inflation.db

The route() dispatcher follows the bcb/sgs pattern: lazy-imports each mode's
module on first dispatch, filters kwargs by the target function's signature,
and returns a structured dict (status / error / traceback on failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "inflation",
    "description": (
        "DDM Inflation - Brazilian inflation indices (IGP-M, IPCA, INPC) "
        "scraped from dadosdemercado.com.br server-rendered HTML. No auth, "
        "no JS. Each index page exposes 2 tables: monthly matrix (year x "
        "month) + historical monthly series (month_value, year_acumulado, "
        "acumulado_12m). Regex-based parser (no BeautifulSoup). "
        "Thread-safe concurrent syncer (3 workers)."
    ),
    "source":  "www.dadosdemercado.com.br/indices/{slug} (HTML scrape, no auth)",
    "storage": "memory_db/ddm/inflation.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync every index in INDEX_CATALOG concurrently (max_workers=3, "
                "~3 HTTP calls). Idempotent via INSERT OR REPLACE on "
                "(slug, ref_date)."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": "Sync one index (full available history from HTML). Idempotent.",
            "include_in_all": True,
            "params": {
                "slug":  "str. DDM index slug (e.g. 'igp-m'). Required.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="sync_index", '
                'params=\'{"slug":"igp-m"}\')',
            ],
        },
        "series": {
            "description": "Query historical monthly observations for an index.",
            "include_in_all": True,
            "params": {
                "slug":  "str. Required.",
                "limit": "int. Number of most-recent obs. Default: 60.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="series", '
                'params=\'{"slug":"ipca","limit":24}\')',
            ],
        },
        "last": {
            "description": "Get the most recent observation for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="last", '
                'params=\'{"slug":"inpc"}\')',
            ],
        },
        "matrix": {
            "description": "Get the monthly matrix (year x month) for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="matrix", '
                'params=\'{"slug":"igp-m"}\')',
            ],
        },
        "search": {
            "description": "Search INDEX_CATALOG by name/slug fragment (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Name/slug fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="search", '
                'params=\'{"query":"IGP"}\')',
            ],
        },
        "summary": {
            "description": "Catalog overview: every index sorted by category.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="summary")',
            ],
        },
        "status": {
            "description": "Show inflation.db stats: per-index row counts + last sync timestamps.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="inflation", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch inflation mode call (sgs pattern: lazy-import + filter kwargs)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_all":
            from data_sources.ddm.inflation.sync_engine import sync_all as _fn
        elif mode == "sync_index":
            from data_sources.ddm.inflation.sync_engine import sync_index as _fn
        elif mode == "series":
            from data_sources.ddm.inflation.query_engine import index_history as _fn
        elif mode == "last":
            from data_sources.ddm.inflation.query_engine import last_value as _fn
        elif mode == "matrix":
            from data_sources.ddm.inflation.query_engine import monthly_matrix as _fn
        elif mode == "search":
            from data_sources.ddm.inflation.query_engine import search as _fn
        elif mode == "summary":
            from data_sources.ddm.inflation.query_engine import summary as _fn
        elif mode == "status":
            from data_sources.ddm.inflation.status_reporter import status as _fn
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
            "sub_domain": "inflation",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
