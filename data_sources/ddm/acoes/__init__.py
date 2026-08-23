"""data_sources/ddm/acoes/__init__.py -- Acoes sub-domain manifest + router.

DDM Acoes = Brazilian B3 tradable stocks scraped from dadosdemercado.com.br.
Single page at /acoes lists every B3 listed stock (~380 rows) with:
  - Ticker   (e.g. 'PETR4')
  - Nome     (e.g. 'Petrobras')
  - Negocios (number of trades, integer)
  - Ultima   (last price in BRL, e.g. 44.30)
  - Variacao (intraday % change, can be negative)

Pre-sorted by Negocios DESC (most-traded first). No pagination - all rows
are on one page. Server-rendered HTML, no JS, no auth.

8 modes: sync_all, sync_index, stocks, last, search, summary, status, ticker.
sync_all fetches the single acoes page; sync_index is an alias for parity
with the other DDM sub-domains (inflation/juros/poupanca). Both `last`
and `ticker` modes return the most-recent snapshot for a single ticker
(`ticker` is the user-facing alias for `last`; same underlying
`last_value` query function, just a more memorable name).

Data source: www.dadosdemercado.com.br/acoes (HTML scrape)
Storage:     memory_db/ddm/acoes.db

The route() dispatcher follows the bcb/sgs + ddm/inflation pattern:
lazy-imports each mode's module on first dispatch, filters kwargs by the
target function's signature, and returns a structured dict (status / error /
traceback on failure).

Auto-discovered by data_sources/ddm/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations

from data_sources.ddm._base.route_base import make_ddm_route

MANIFEST = {
    "sub_domain":  "acoes",
    "description": (
        "DDM Acoes - all B3 tradable stocks (~380) scraped from "
        "dadosdemercado.com.br/acoes. Single server-rendered HTML table "
        "(id='stocks') with columns: Ticker | Nome | Negocios | "
        "Ultima (R$) | Variacao (%). Pre-sorted by Negocios DESC. No "
        "pagination, no auth, no JS. Regex-based parser (no BeautifulSoup). "
        "Variation can be negative (red in UI). Numeric cells get a "
        "data-value attribute for accurate sorting."
    ),
    "source":  "www.dadosdemercado.com.br/acoes (HTML scrape, no auth)",
    "storage": "memory_db/ddm/acoes.db",
    "modes": {
        "sync_all": {
            "description": (
                "Fetch the single /acoes page, parse the stocks table, and "
                "INSERT OR REPLACE all rows. Idempotent via PK on ticker."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="sync_all")',
            ],
        },
        "sync_index": {
            "description": (
                "Alias for sync_all (kept for parity with the other DDM "
                "sub-domains; the acoes page is a single page, not per-index)."
            ),
            "include_in_all": True,
            "params": {
                "slug":  "str. Ignored (only 'acoes' is supported). Optional.",
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="sync_index", '
                'params=\'{"slug":"acoes"}\')',
            ],
        },
        "stocks": {
            "description": (
                "List all stocks sorted by the specified column + direction. "
                "Default sort: Negocios DESC (matches DDM page order)."
            ),
            "include_in_all": True,
            "params": {
                "order_by":  "str. One of: ticker, name, negocios, last_price, variation. Default: 'negocios'.",
                "direction": "str. 'asc' or 'desc'. Default: 'desc'.",
                "limit":     "int. Max results. 0 = all. Default: 0.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="stocks", '
                'params=\'{"order_by":"variation","direction":"desc"}\')',
            ],
        },
        "last": {
            "description": "Get the most recent snapshot for a single ticker.",
            "include_in_all": True,
            "params": {
                "ticker": "str. Required (e.g. 'PETR4').",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="last", '
                'params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "search": {
            "description": "Search stocks by ticker or name (case-insensitive).",
            "include_in_all": False,
            "params": {
                "query": "str. Ticker/name fragment. Required.",
                "limit": "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="search", '
                'params=\'{"query":"petro"}\')',
            ],
        },
        "summary": {
            "description": "Overview: total stocks, most traded, biggest gainer, biggest loser.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="summary")',
            ],
        },
        "status": {
            "description": "Show acoes.db stats: row count + last sync timestamp.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="status")',
            ],
        },
        "ticker": {
            "description": (
                "Get the most recent snapshot for a single ticker. "
                "User-facing alias for `last` (same underlying query)."
            ),
            "include_in_all": True,
            "params": {
                "ticker": "str. Required (e.g. 'PETR4').",
            },
            "examples": [
                'data_source(domain="ddm", sub_domain="acoes", mode="ticker", '
                'params=\'{"ticker":"PETR4"}\')',
            ],
        },
    },
}


# mode -> (module_path, function_name) lazy-import map.
_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.acoes.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.acoes.sync_engine",     "sync_index"),
    "stocks":     ("data_sources.ddm.acoes.query_engine",    "stocks_list"),
    "last":       ("data_sources.ddm.acoes.query_engine",    "last_value"),
    "search":     ("data_sources.ddm.acoes.query_engine",    "search"),
    "summary":    ("data_sources.ddm.acoes.query_engine",    "summary"),
    "ticker":     ("data_sources.ddm.acoes.query_engine",    "last_value"),
    "status":     ("data_sources.ddm.acoes.status_reporter", "status"),
}

route = make_ddm_route(
    sub_domain="acoes",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
