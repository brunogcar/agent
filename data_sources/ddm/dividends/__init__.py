"""data_sources/ddm/dividends/__init__.py -- Dividends sub-domain manifest + router.

DDM Dividends = Brazilian corporate dividend events scraped from the DDM
"agenda de dividendos" page. Single HTML page, single table, ~200 rows.

URL: https://www.dadosdemercado.com.br/agenda-de-dividendos
Table class: normal-table
Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento
Tipos: Dividendo | JCP (Juros sobre Capital Proprio)

8 modes: sync_all, sync_index, dividends, last, search, summary, status, ticker.

The route() dispatcher follows the bcb/sgs + ddm/inflation/juros/poupanca
pattern: lazy-imports each mode's module on first dispatch, filters kwargs
by the target function's signature, and returns a structured dict
(status / error / traceback on failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations

from data_sources.ddm._base.route_base import make_ddm_route

MANIFEST = {
    "sub_domain":  "dividends",
    "description": (
        "DDM Dividends - Brazilian corporate dividend events scraped from "
        "dadosdemercado.com.br/agenda-de-dividendos. Single HTML page, "
        "1 table (class normal-table), ~200 rows. 2 tipos: Dividendo + "
        "JCP (Juros sobre Capital Proprio). Columns: Codigo | Tipo | "
        "Valor (R$) | Registro | Ex | Pagamento. Values stored as REAL "
        "(R$), dates stored as YYYY-MM-DD in the DB. Regex-based parser "
        "(no BeautifulSoup). Thread-safe concurrent fetcher (5 workers). "
        "Sorter table feature: dashboard emits section.sortable=True so "
        "the existing macros.html sortTable() can sort columns client-side."
    ),
    "source":  "www.dadosdemercado.com.br/agenda-de-dividendos (HTML scrape, no auth)",
    "storage": "memory_db/ddm/dividends.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync the entire dividend agenda page (1 HTTP call). "
                "Idempotent via INSERT OR REPLACE on "
                "(ticker, record_date, tipo)."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": (
                "Alias for sync_all (dividends page is a single page, "
                "so slug='dividends' is the only valid value)."
            ),
            "include_in_all": True,
            "params": {
                "slug":  "str. Must be 'dividends'. Default: 'dividends'.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="sync_index", '
                'params=\'{"slug":"dividends"}\')',
            ],
        },
        "dividends": {
            "description": (
                "List all dividends sorted by a column. Returns a "
                "structured payload of dividend rows (ticker, tipo, "
                "value, record_date, ex_date, payment_date)."
            ),
            "include_in_all": True,
            "params": {
                "order_by":   "str. Sort key: 'value' | 'ticker' | 'tipo' | "
                              "'record_date' | 'ex_date' | 'payment_date'. "
                              "Default: 'value'.",
                "direction":  "str. 'desc' | 'asc'. Default: 'desc'.",
                "limit":      "int. Max rows. 0 = all. Default: 0.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="dividends")',
            ],
        },
        "last": {
            "description": (
                "Get the latest dividends for a specific ticker "
                "(most recent by record_date DESC)."
            ),
            "include_in_all": True,
            "params": {
                "ticker": "str. B3 ticker (e.g. 'BBDC3'). Required.",
                "limit":  "int. Max rows. Default: 10.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="last", '
                'params=\'{"ticker":"BBDC3"}\')',
            ],
        },
        "search": {
            "description": "Search dividends by ticker fragment (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Ticker fragment. Required.",
                "limit": "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="search", '
                'params=\'{"query":"PETR"}\')',
            ],
        },
        "summary": {
            "description": (
                "Overview stats: total rows, total value (sum), biggest "
                "dividend, next payment date. Plus counts by tipo "
                "(Dividendo vs JCP)."
            ),
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="summary")',
            ],
        },
        "status": {
            "description": "Show dividends.db stats: total rows + last sync timestamp.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="status")',
            ],
        },
        "ticker": {
            "description": (
                "All dividends for a specific ticker (all dates, all tipos). "
                "Sorted by record_date DESC."
            ),
            "include_in_all": False,
            "params": {
                "ticker": "str. B3 ticker (e.g. 'PETR4'). Required.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="dividends", mode="ticker", '
                'params=\'{"ticker":"PETR4"}\')',
            ],
        },
    },
}


# mode -> (module_path, function_name) lazy-import map.
_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.dividends.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.dividends.sync_engine",     "sync_all"),
    "dividends":  ("data_sources.ddm.dividends.query_engine",    "dividends_list"),
    "last":       ("data_sources.ddm.dividends.query_engine",    "last_value"),
    "search":     ("data_sources.ddm.dividends.query_engine",    "search"),
    "summary":    ("data_sources.ddm.dividends.query_engine",    "summary"),
    "ticker":     ("data_sources.ddm.dividends.query_engine",    "ticker_history"),
    "status":     ("data_sources.ddm.dividends.status_reporter", "status"),
}

route = make_ddm_route(
    sub_domain="dividends",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
