"""data_sources/b3/api/__init__.py -- B3 API sub-domain manifest and router.

B3 market data via the new paginated JSON API (the old 3-step CSV download
flow is broken — B3 migrated to a React SPA with a JSON table API).

Data source: https://arquivos.b3.com.br/tabelas/table/{tableName}/{date}/{page}
Storage: memory_db/b3/{table}.db

Tables:
  instruments  → tickers, ISIN, company names, segment, governance
  trades       → daily prices, volume, VWAP
  after_hours  → after-hours session trades
  derivatives  → open interest (futures, options)
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "api",
    "description": (
        "B3 market data via paginated JSON API. "
        "instruments: tickers + company names. trades: daily prices + volume. "
        "after_hours + derivatives also available."
    ),
    "source":  "arquivos.b3.com.br/tabelas/table/ -> b3/{table}.db",
    "storage": "memory_db/b3/{table}.db",
    "modes": {
        "sync": {
            "description": "Download B3 data via JSON API and store to SQLite. Default: instruments for today.",
            "include_in_all": True,
            "params": {
                "table":    "str. instruments | trades | after_hours | derivatives. Default: instruments.",
                "date_str": "str. YYYY-MM-DD. Default: today.",
                "force":    "bool. Re-download even if already synced. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="api", mode="sync")',
                'data_source(domain="b3", sub_domain="api", mode="sync", params=\'{"table":"trades"}\')',
                'data_source(domain="b3", sub_domain="api", mode="sync", params=\'{"table":"instruments","date_str":"2026-07-22"}\')',
            ],
        },
        "status": {
            "description": "Show sync status for all B3 tables (row counts, last sync dates).",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="b3", sub_domain="api", mode="status")',
            ],
        },
        "query": {
            "description": "Query B3 data from local SQLite. Filter by ticker or column values.",
            "include_in_all": False,
            "params": {
                "table":   "str. instruments | trades | after_hours | derivatives. Default: instruments.",
                "ticker":  "str. Ticker symbol (e.g., PETR4). Empty = all.",
                "columns": "list[str]. Specific columns to return. Default: all.",
                "filters": "dict. {column: value} for additional filtering.",
                "limit":   "int. Max rows. Default: 100.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="api", mode="query", params=\'{"ticker":"PETR4"}\')',
                'data_source(domain="b3", sub_domain="api", mode="query", params=\'{"table":"trades","ticker":"VALE3"}\')',
            ],
        },
        "lookup_ticker": {
            "description": "Look up a single ticker in the instruments table.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required. Ticker symbol (e.g., PETR4).",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="api", mode="lookup_ticker", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "search_company": {
            "description": "Search instruments by company name fragment.",
            "include_in_all": False,
            "params": {
                "name":  "str. Required. Company name fragment.",
                "limit": "int. Max results. Default: 20.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="api", mode="search_company", params=\'{"name":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch b3/api mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.b3.api.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.b3.api.query_engine import status as _status
            return _status()

        elif mode == "query":
            from data_sources.b3.api.query_engine import query as _query
            sig = inspect.signature(_query)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _query(**filtered)

        elif mode == "lookup_ticker":
            from data_sources.b3.api.query_engine import lookup_ticker as _lookup
            sig = inspect.signature(_lookup)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _lookup(**filtered)

        elif mode == "search_company":
            from data_sources.b3.api.query_engine import search_company as _search
            sig = inspect.signature(_search)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _search(**filtered)

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "api",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
