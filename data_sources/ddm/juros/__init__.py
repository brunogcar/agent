"""data_sources/ddm/juros/__init__.py -- Juros sub-domain manifest + router.

DDM Juros = Brazilian interest-rate indices scraped from dadosdemercado.com.br.
Each index has its own page with ONLY 1 HTML table (the monthly matrix -
id="index-values"). There is NO historical table on these pages and NO "Ano"
acumulado column (these are daily rates, not cumulative variations).

3 curated indices:
  - selic       (Taxa Selic diaria, % a.a.)
  - meta-selic  (Meta para taxa Selic - Copom, % a.a.)
  - cdi         (Certificado de Deposito Interbancario, % a.a.)

8 modes: sync_all, sync_index, series, last, matrix, search, summary, status.

Data source: www.dadosdemercado.com.br/indices/{slug} (HTML scrape)
Storage:     memory_db/ddm/juros.db

Because the page only ships the monthly matrix, the historical series is
DERIVED from it at parse time (see fetcher.flatten_matrix_to_observations):
  - month_value   = cell value (daily rate %)
  - media_no_ano  = AVERAGE of all months in the same year UP TO that month
  - media_12m     = AVERAGE of the last 12 months (rolling)

These mirror the Google Sheet formulas used by the original analyst:
  - "Media no ano (%)":     AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))
  - "Media 12 meses (%)":   AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))

The route() dispatcher follows the bcb/sgs pattern: lazy-imports each mode's
module on first dispatch, filters kwargs by the target function's signature,
and returns a structured dict (status / error / traceback on failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations

from data_sources.ddm._base.route_base import make_ddm_route

MANIFEST = {
    "sub_domain":  "juros",
    "description": (
        "DDM Juros - Brazilian interest-rate indices (Selic, Meta Selic, "
        "CDI) scraped from dadosdemercado.com.br server-rendered HTML. No "
        "auth, no JS. Each index page exposes ONLY 1 table (the monthly "
        "matrix - no historical table, no 'Ano' acumulado column). The "
        "historical series (month_value, media_no_ano, media_12m) is "
        "DERIVED from the matrix at parse time. Regex-based parser (no "
        "BeautifulSoup). Thread-safe concurrent syncer (3 workers)."
    ),
    "source":  "www.dadosdemercado.com.br/indices/{slug} (HTML scrape, no auth)",
    "storage": "memory_db/ddm/juros.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync every index in JUROS_CATALOG concurrently (max_workers=3, "
                "~3 HTTP calls). Idempotent via INSERT OR REPLACE on "
                "(slug, ref_date)."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": "Sync one index (matrix only - historical series derived). Idempotent.",
            "include_in_all": True,
            "params": {
                "slug":  "str. DDM juros slug (e.g. 'selic'). Required.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="sync_index", '
                'params=\'{"slug":"selic"}\')',
            ],
        },
        "series": {
            "description": "Query derived historical monthly observations for an index.",
            "include_in_all": True,
            "params": {
                "slug":  "str. Required.",
                "limit": "int. Number of most-recent obs. Default: 60.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="series", '
                'params=\'{"slug":"cdi","limit":24}\')',
            ],
        },
        "last": {
            "description": "Get the most recent derived observation for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="last", '
                'params=\'{"slug":"meta-selic"}\')',
            ],
        },
        "matrix": {
            "description": "Get the monthly matrix (year x month, NO Ano column) for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="matrix", '
                'params=\'{"slug":"selic"}\')',
            ],
        },
        "search": {
            "description": "Search JUROS_CATALOG by name/slug fragment (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Name/slug fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="search", '
                'params=\'{"query":"selic"}\')',
            ],
        },
        "summary": {
            "description": "Catalog overview: every index sorted by category.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="summary")',
            ],
        },
        "status": {
            "description": "Show juros.db stats: per-index row counts + last sync timestamps.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="juros", mode="status")',
            ],
        },
    },
}


# mode -> (module_path, function_name) lazy-import map.
_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.juros.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.juros.sync_engine",     "sync_index"),
    "series":     ("data_sources.ddm.juros.query_engine",    "juros_history"),
    "last":       ("data_sources.ddm.juros.query_engine",    "last_value"),
    "matrix":     ("data_sources.ddm.juros.query_engine",    "monthly_matrix"),
    "search":     ("data_sources.ddm.juros.query_engine",    "search"),
    "summary":    ("data_sources.ddm.juros.query_engine",    "summary"),
    "status":     ("data_sources.ddm.juros.status_reporter", "status"),
}

route = make_ddm_route(
    sub_domain="juros",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
