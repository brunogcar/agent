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

from data_sources.ddm._base.route_base import make_ddm_route

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


# mode -> (module_path, function_name) lazy-import map.
# Import is deferred to inside route() to avoid import-time circular deps
# (sync_engine imports catalog imports fetcher imports _parsers etc.).
_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.inflation.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.inflation.sync_engine",     "sync_index"),
    "series":     ("data_sources.ddm.inflation.query_engine",    "index_history"),
    "last":       ("data_sources.ddm.inflation.query_engine",    "last_value"),
    "matrix":     ("data_sources.ddm.inflation.query_engine",    "monthly_matrix"),
    "search":     ("data_sources.ddm.inflation.query_engine",    "search"),
    "summary":    ("data_sources.ddm.inflation.query_engine",    "summary"),
    "status":     ("data_sources.ddm.inflation.status_reporter", "status"),
}

route = make_ddm_route(
    sub_domain="inflation",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
