"""data_sources/b3/cotahist/__init__.py -- COTAHIST sub-domain manifest + router.

B3 official historical trade data. Annual ZIP files with every trade for
every B3-listed security (stocks, bonds, funds, options, FIIs) since 1986.
We sync 2010-present (matching CVM DFP).

Source: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP
Storage: memory_db/b3/cotahist.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "cotahist",
    "description": (
        "B3 official historical trade data (COTAHIST). Annual ZIP files with "
        "OHLCV for every B3 security since 2010. Fixed-width format. "
        "Best for backtesting, historical analysis, instrument metadata."
    ),
    "source":  "bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP",
    "storage": "memory_db/b3/cotahist.db",
    "modes": {
        "sync": {
            "description": "Download + parse COTAHIST for one or more years (2010-present). ~87MB ZIP per year.",
            "include_in_all": False,
            "params": {
                "year":  "int. Single year (e.g., 2025). Ignored if years given.",
                "years": "list[int]. Multiple years. Takes precedence over year.",
                "force": "bool. Re-download even if already synced. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="cotahist", mode="sync", params=\'{"year":2025}\')',
                'data_source(domain="b3", sub_domain="cotahist", mode="sync", params=\'{"years":[2023,2024,2025]}\')',
            ],
        },
        "query": {
            "description": "Query historical OHLCV from local DB. Filter by ticker, date range, or year.",
            "include_in_all": True,
            "params": {
                "ticker":     "str. Ticker symbol (PETR4). Empty = all.",
                "date_from":  "str. Start date YYYY-MM-DD.",
                "date_to":    "str. End date YYYY-MM-DD.",
                "year":       "int. Filter by year (e.g., 2025). Takes precedence over date_from/date_to.",
                "limit":      "int. Max rows. Default: 100.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="cotahist", mode="query", params=\'{"ticker":"PETR4","year":2025}\')',
                'data_source(domain="b3", sub_domain="cotahist", mode="query", params=\'{"ticker":"VALE3","date_from":"2025-01-01","date_to":"2025-06-30"}\')',
            ],
        },
        "status": {
            "description": "Show cotahist.db stats: years synced, row counts, date range, distinct tickers.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="b3", sub_domain="cotahist", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch cotahist mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from data_sources.b3.cotahist.sync_engine import sync, sync_full_history
    from data_sources.b3.cotahist.query_engine import query
    from data_sources.b3.cotahist.status_reporter import status

    dispatch = {
        "sync": sync,
        "query": query,
        "status": status,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "cotahist",
                "mode": mode, "error": str(e)}
