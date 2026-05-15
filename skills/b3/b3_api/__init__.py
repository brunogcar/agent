"""
skills/b3/b3_api/__init__.py -- B3 API sub-domain manifest.

Routes skill(domain="b3", sub_domain="b3_api", mode=...) calls.
"""

from __future__ import annotations
import inspect
from skills.b3.b3_api.b3_api import sync, query, status as b3_status

MANIFEST = {
    "sub_domain":  "b3_api",
    "description": "B3 official public data API. Downloads daily CSVs and queries local SQLite.",
    "source":      "arquivos.b3.com.br (no auth required)",
    "storage":     "memory_db/b3/*.db",

    "modes": {
        "sync": {
            "fn":             sync,
            "description":    "Download today's B3 files and store to SQLite.",
            "include_in_all": True,
            "params": {
                "files": "list of file names. Default: all 5.",
                "force": "bool. Re-download even if current. Default: False.",
            },
            "examples": [
                'skill(domain="b3", sub_domain="b3_api", mode="sync")',
                'skill(domain="b3", sub_domain="b3_api", mode="sync", params=\'{"files":["Instruments","Trades"]}\')',
            ],
        },
        "query": {
            "fn":             query,
            "description":    "Query local B3 data. Use ticker for cross-file lookup.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Ticker symbol e.g. PETR4.",
                "files":   "list. Files to query. Default: [Instruments, Trades].",
                "filters": "dict. Column filters e.g. {\"SgmtNm\": \"Equity - Cash\"}.",
                "columns": "list. Columns to return. Default: all.",
                "limit":   "int. Max rows. Default: 100.",
            },
            "examples": [
                'skill(domain="b3", sub_domain="b3_api", mode="query", params=\'{"ticker":"PETR4"}\')',
                'skill(domain="b3", sub_domain="b3_api", mode="query", params=\'{"files":["Trades"],"limit":20}\')',
            ],
        },
        "status": {
            "fn":             b3_status,
            "description":    "Show sync status for all B3 files.",
            "include_in_all": True,
            "params":         {},
            "examples": [
                'skill(domain="b3", sub_domain="b3_api", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    if not mode:
        return {"status": "error", "error": "mode is required for b3_api. Options: sync, query, status"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for b3_api. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "b3_api", "mode": mode, "error": str(e)}
