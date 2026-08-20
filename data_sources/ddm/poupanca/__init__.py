"""data_sources/ddm/poupanca/__init__.py -- Poupanca sub-domain manifest + router.

DDM Poupanca = Brazilian savings-account monthly yield scraped from
dadosdemercado.com.br. The poupanca page has ONLY 1 HTML table (the monthly
matrix - id="index-values"). There is NO historical table on the page and
NO "Ano" acumulado column.

1 curated index:
  - poupanca  (Poupanca - rendimento mensal, %)

8 modes: sync_all, sync_index, series, last, matrix, search, summary, status.

Data source: www.dadosdemercado.com.br/indices/poupanca (HTML scrape)
Storage:     memory_db/ddm/poupanca.db

Because the page only ships the monthly matrix, the historical series is
DERIVED from it at parse time (see fetcher.flatten_matrix_to_observations):
  - month_value        = cell value (monthly yield %)
  - acumulado_no_ano   = SUM of all months in the same year UP TO that month
                         (year-to-date cumulative return)
  - acumulado_12m      = SUM of the last 12 months (rolling cumulative return)

These mirror the Google Sheet formulas used by the original analyst:
  - "Acumulado no ano (%)":     SUM(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))
  - "Acumulado 12 meses (%)":   SUM(FILTER(B:B, A:A<=d, A:A>=d-365))

IMPORTANT: Poupanca uses SUM (not AVERAGE like juros) because the monthly
yield is already a percentage return - summing them produces the cumulative
return. This matches the analyst's Google Sheet layout.

The route() dispatcher follows the bcb/sgs pattern: lazy-imports each mode's
module on first dispatch, filters kwargs by the target function's signature,
and returns a structured dict (status / error / traceback on failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "poupanca",
    "description": (
        "DDM Poupanca - Brazilian savings-account monthly yield scraped from "
        "dadosdemercado.com.br server-rendered HTML. No auth, no JS. The "
        "poupanca page exposes ONLY 1 table (the monthly matrix - no "
        "historical table, no 'Ano' acumulado column). The historical series "
        "(month_value, acumulado_no_ano, acumulado_12m) is DERIVED from the "
        "matrix at parse time using SUM (NOT AVERAGE - poupanca is a "
        "percentage return, so summing produces the cumulative return). "
        "Regex-based parser (no BeautifulSoup). Thread-safe concurrent "
        "syncer (3 workers)."
    ),
    "source":  "www.dadosdemercado.com.br/indices/poupanca (HTML scrape, no auth)",
    "storage": "memory_db/ddm/poupanca.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync every index in POUPANCA_CATALOG concurrently "
                "(max_workers=3, ~1 HTTP call). Idempotent via "
                "INSERT OR REPLACE on (slug, ref_date)."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": "Sync one index (matrix only - historical series derived). Idempotent.",
            "include_in_all": True,
            "params": {
                "slug":  "str. DDM poupanca slug (e.g. 'poupanca'). Required.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="sync_index", '
                'params=\'{"slug":"poupanca"}\')',
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
                'data_source(domain="ddm", sub_domain="poupanca", mode="series", '
                'params=\'{"slug":"poupanca","limit":24}\')',
            ],
        },
        "last": {
            "description": "Get the most recent derived observation for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="last", '
                'params=\'{"slug":"poupanca"}\')',
            ],
        },
        "matrix": {
            "description": "Get the monthly matrix (year x month, NO Ano column) for an index.",
            "include_in_all": True,
            "params": {
                "slug": "str. Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="matrix", '
                'params=\'{"slug":"poupanca"}\')',
            ],
        },
        "search": {
            "description": "Search POUPANCA_CATALOG by name/slug fragment (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Name/slug fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="search", '
                'params=\'{"query":"poup"}\')',
            ],
        },
        "summary": {
            "description": "Catalog overview: every index sorted by category.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="summary")',
            ],
        },
        "status": {
            "description": "Show poupanca.db stats: per-index row counts + last sync timestamps.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="poupanca", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch poupanca mode call (sgs pattern: lazy-import + filter kwargs)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_all":
            from data_sources.ddm.poupanca.sync_engine import sync_all as _fn
        elif mode == "sync_index":
            from data_sources.ddm.poupanca.sync_engine import sync_index as _fn
        elif mode == "series":
            from data_sources.ddm.poupanca.query_engine import poupanca_history as _fn
        elif mode == "last":
            from data_sources.ddm.poupanca.query_engine import last_value as _fn
        elif mode == "matrix":
            from data_sources.ddm.poupanca.query_engine import monthly_matrix as _fn
        elif mode == "search":
            from data_sources.ddm.poupanca.query_engine import search as _fn
        elif mode == "summary":
            from data_sources.ddm.poupanca.query_engine import summary as _fn
        elif mode == "status":
            from data_sources.ddm.poupanca.status_reporter import status as _fn
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
            "sub_domain": "poupanca",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
