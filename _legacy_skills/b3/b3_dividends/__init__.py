"""
skills/b3/b3_dividends/__init__.py
B3 dividends / corporate actions sub-domain.

Routes skill(domain='b3', sub_domain='b3_dividends', mode=...) calls.
Storage: memory_db/b3/dividends.db (isolated, never touches existing DBs).

Architecture:
  - api_client.py    : B3 HTTP layer with retry
  - parser.py        : JSON → normalized rows (date normalization, validation)
  - storage.py       : SQLite operations (chunked insert, type coercion)
  - query_engine.py  : SQL builder with filters and date ranges
  - sync_engine.py   : Orchestrates download → parse → store → state
  - status_reporter.py : Accurate per-schema, per-ticker status
  - dividends_catalog.py : Schema registry (tables, columns, types)

Adapted from Google Sheets: doGetProventos() → fillCashDividends(), fillStockDividends(), fillSubscriptions()
"""
from __future__ import annotations
import inspect

from skills.b3.b3_dividends.sync_engine import sync, sync_all
from skills.b3.b3_dividends.query_engine import query
from skills.b3.b3_dividends.status_reporter import status

MANIFEST = {
    "sub_domain": "b3_dividends",
    "description": "B3 corporate actions: cash dividends, stock dividends, subscription rights.",
    "source": "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{base64}",
    "storage": "memory_db/b3/dividends.db",
    "modes": {
        "sync": {
            "fn": sync,
            "description": "Download and store dividends data for a specific ticker.",
            "include_in_all": True,  # Changed from False — enables automatic sync
            "params": {
                "ticker": "str. Full ticker (e.g. 'PETR4', 'VALE3', 'WEGE3', 'SAPR11'). First 4 chars are the issuing company.",
                "force": "bool. Redownload if already synced. Default: False.",
            },
            "examples": [
                'skill(domain="b3", sub_domain="b3_dividends", mode="sync", params={"ticker":"PETR4"})',
                'skill(domain="b3", sub_domain="b3_dividends", mode="sync", params={"ticker":"VALE3","force":True})',
            ],
        },
        "query": {
            "fn": query,
            "description": "Query local dividends data with filters.",
            "include_in_all": True,
            "params": {
                "ticker": "str. Filter by full ticker (e.g. 'PETR4').",
                "dividend_type": "str. Filter by type: cash, stock, subscription.",
                "start_date": "str. Filter by approved_on >= YYYY-MM-DD.",
                "end_date": "str. Filter by approved_on <= YYYY-MM-DD.",
                "filters": "dict. Additional {column: value} equality filters.",
                "columns": "list. Specific columns to return.",
                "limit": "int. Max rows per schema. Default: 100.",
            },
            "examples": [
                'skill(domain="b3", sub_domain="b3_dividends", mode="query", params={"ticker":"PETR4","dividend_type":"cash"})',
                'skill(domain="b3", sub_domain="b3_dividends", mode="query", params={"start_date":"2024-01-01","end_date":"2024-12-31"})',
            ],
        },
        "status": {
            "fn": status,
            "description": "Show sync status for dividends.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'skill(domain="b3", sub_domain="b3_dividends", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Route skill calls to the appropriate mode function.

    Args:
        mode: One of "sync", "query", "status".
        **kwargs: Mode-specific parameters.

    Returns:
        Result dict from the mode function, or error dict if mode is unknown.

    Note:
        Filters kwargs to only pass accepted parameters to the target function,
        preventing TypeError from unexpected arguments.
    """
    kwargs.pop("sub_domain", None)
    if not mode or mode not in MANIFEST["modes"]:
        return {
            "status": "error",
            "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}",
        }
    fn = MANIFEST["modes"][mode]["fn"]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {
            "status": "error",
            "sub_domain": MANIFEST["sub_domain"],
            "mode": mode,
            "error": str(e),
        }
