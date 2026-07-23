"""data_sources/b3/dividends/__init__.py -- B3 dividends sub-domain manifest and router.

B3 corporate actions / dividends via per-ticker JSON API.
Returns cash dividends, stock dividends, and subscription rights.

Data source: sistemaswebb3-listados.b3.com.br (per-ticker JSON, not paginated)
Storage: memory_db/b3/dividends.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "dividends",
    "description": (
        "B3 corporate actions: cash dividends, stock dividends, subscription rights. "
        "Per-ticker JSON API (not paginated). Sync by ticker."
    ),
    "source":  "sistemaswebb3-listados.b3.com.br -> dividends.db",
    "storage": "memory_db/b3/dividends.db",
    "modes": {
        "sync": {
            "description": "Download dividends for a specific ticker. Per-ticker (not bulk).",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required. Full ticker (e.g., PETR4, VALE3).",
                "force":  "bool. Re-download even if already synced. Default: false.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="sync", params=\'{"ticker":"PETR4"}\')',
                'data_source(domain="b3", sub_domain="dividends", mode="sync", params=\'{"ticker":"VALE3","force":true}\')',
            ],
        },
        "status": {
            "description": "Show dividends DB stats: synced tickers, row counts per table.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="status")',
            ],
        },
        "dividends": {
            "description": "Query cash dividends for a ticker.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
                "limit":  "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="dividends", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "stock_dividends": {
            "description": "Query stock dividends (bonus shares) for a ticker.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
                "limit":  "int. Default: 50.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="stock_dividends", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "subscriptions": {
            "description": "Query subscription rights for a ticker.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
                "limit":  "int. Default: 50.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="subscriptions", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "company_info": {
            "description": "Query company info (codeCVM, shares, capital, segment) stored during dividends sync.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
            },
            "examples": [
                'data_source(domain="b3", sub_domain="dividends", mode="company_info", params=\'{"ticker":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch b3/dividends mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.b3.dividends.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.b3.dividends.query_engine import status as _status
            return _status()

        elif mode == "dividends":
            from data_sources.b3.dividends.query_engine import dividends as _div
            sig = inspect.signature(_div)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _div(**filtered)

        elif mode == "stock_dividends":
            from data_sources.b3.dividends.query_engine import stock_dividends as _sd
            sig = inspect.signature(_sd)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sd(**filtered)

        elif mode == "subscriptions":
            from data_sources.b3.dividends.query_engine import subscriptions as _sub
            sig = inspect.signature(_sub)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sub(**filtered)

        elif mode == "company_info":
            from data_sources.b3.dividends.query_engine import company_info as _ci
            sig = inspect.signature(_ci)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _ci(**filtered)

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "dividends",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
