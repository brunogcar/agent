"""data_sources/b3/brapi/__init__.py -- brapi.dev sub-domain manifest + router.

brapi.dev is a Brazilian-market REST API. Free tier covers main tickers.
Replaces the 7,138-page InstrumentsConsolidated sync with 1 call.

5 modes: sync_tickers, sync_history, quote, history, status, tickers.

Data source: brapi.dev (live REST API)
Storage: memory_db/b3/brapi.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "brapi",
    "description": (
        "brapi.dev API — current quotes, historical OHLCV, ticker list. "
        "Free tier (PETR4/VALE3/ITUB4/MGLU3). Full coverage with free signup. "
        "Replaces 7138-page instruments sync with 1 call."
    ),
    "source":  "brapi.dev (live REST API)",
    "storage": "memory_db/b3/brapi.db",
    "modes": {
        "sync_tickers": {
            "description": "Sync the full ticker list (~1,796 tickers in 1 call). Replaces InstrumentsConsolidated.",
            "include_in_all": False,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="sync_tickers")',
            ],
        },
        "sync_history": {
            "description": "Sync historical OHLCV for a ticker from brapi.dev.",
            "include_in_all": False,
            "params": {
                "ticker":   "str. B3 ticker (PETR4). Required.",
                "range":    "str. Time range: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max. Default: 1y.",
                "interval": "str. Bar interval: 1d, 5d, 1wk, 1mo, 3mo. Default: 1d.",
                "force":    "bool. Re-download even if already synced. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="sync_history", params=\'{"ticker":"PETR4"}\')',
                'data_source(domain="b3", sub_domain="brapi", mode="sync_history", params=\'{"ticker":"PETR4","range":"5y"}\')',
            ],
        },
        "quote": {
            "description": "Get latest quote (price, market cap, P/E, volume). Tries local DB first, then live.",
            "include_in_all": True,
            "params": {
                "ticker": "str. Required.",
                "force":  "bool. Always fetch live. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="quote", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "history": {
            "description": "Query historical OHLCV from local DB.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
                "days":   "int. Number of days. Default: 30.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="history", params=\'{"ticker":"PETR4","days":90}\')',
            ],
        },
        "tickers": {
            "description": "List all synced tickers.",
            "include_in_all": False,
            "params": {},
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="tickers")',
            ],
        },
        "status": {
            "description": "Show brapi.db stats (tickers, OHLCV rows, last sync).",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="b3", sub_domain="brapi", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch brapi mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from data_sources.b3.brapi.sync_engine import sync_tickers, sync_history
    from data_sources.b3.brapi.query_engine import quote, history, tickers
    from data_sources.b3.brapi.status_reporter import status

    dispatch = {
        "sync_tickers": sync_tickers,
        "sync_history": sync_history,
        "quote": quote,
        "history": history,
        "tickers": tickers,
        "status": status,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "brapi",
                "mode": mode, "error": str(e)}
