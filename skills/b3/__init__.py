"""
skills/b3/__init__.py -- B3 domain manifest.

Exposes the domain metadata the dispatcher.py uses to:
  1. Route skill(domain="b3_api", mode=...) calls to the right function
  2. Build the dynamic docstring shown to the LLM
  3. Validate mode and parameter names before calling anything

ADDING A NEW MODE
-----------------
Add an entry to MANIFEST["modes"]. The dispatcher picks it up automatically.
No changes to dispatcher.py needed.

DECISION: __init__.py owns routing, not b3_api.py.
b3_api.py is a pure data module (sync, query, status functions).
This keeps b3_api.py importable and testable without the dispatcher machinery.
"""

from __future__ import annotations

from skills.b3.b3_api import sync, query, status


# ---------------------------------------------------------------------------
# Domain manifest -- read by dispatcher.py to build routing + docstring
# ---------------------------------------------------------------------------

MANIFEST: dict = {
    "domain":      "b3_api",
    "description": "B3 (Brasil Bolsa Balcao) official public data API. Downloads daily CSVs and queries local SQLite storage.",
    "source":      "arquivos.b3.com.br (official B3 public API, no auth required)",
    "storage":     "memory_db/b3/*.db (SQLite, one file per dataset)",

    "modes": {

        "sync": {
            "fn":          sync,
            "description": "Download today's B3 files and store to SQLite. Safe to re-run (skips if already current).",
            "params": {
                "files": "list of file names to sync. Default: all 5. Options: Instruments, Trades, AfterHours, Derivatives, MarginScenario",
                "force": "bool. If True, re-download even if already synced today. Default: False",
            },
            "examples": [
                'skill(domain="b3_api", mode="sync")',
                'skill(domain="b3_api", mode="sync", files=["Instruments", "Trades"])',
                'skill(domain="b3_api", mode="sync", force=True)',
            ],
        },

        "query": {
            "fn":          query,
            "description": "Query local B3 data. Use ticker= for a full picture of one stock (joins all files). Use files= for table-level queries.",
            "params": {
                "ticker":  "str. Ticker symbol (e.g. PETR4, ITUB3, VALE3). Returns merged data from all requested files.",
                "files":   "list of file names to query. Default: [Instruments, Trades]. Options: Instruments, Trades, AfterHours, Derivatives, MarginScenario",
                "filters": "dict of {column: value} filters applied to the query. E.g. {'SgmtNm': 'Equity - Cash'}",
                "columns": "list of column codes to return. Default: all. E.g. ['TckrSymb', 'CrpnNm', 'LastPric']",
                "limit":   "int. Max rows returned for table queries. Default: 100. Ignored for ticker queries.",
            },
            "examples": [
                'skill(domain="b3_api", mode="query", ticker="PETR4")',
                'skill(domain="b3_api", mode="query", ticker="VALE3", files=["Instruments", "Trades", "Derivatives"])',
                'skill(domain="b3_api", mode="query", files=["Instruments"], filters={"SgmtNm": "Equity - Cash"}, limit=50)',
                'skill(domain="b3_api", mode="query", files=["Trades"], columns=["TckrSymb", "LastPric", "NtlFinVol"], limit=20)',
                'skill(domain="b3_api", mode="query", files=["Derivatives"], filters={"Asst": "PETR"})',
            ],
        },

        "status": {
            "fn":          status,
            "description": "Show sync status for all B3 files: last sync date, row counts, DB sizes.",
            "params": {},
            "examples": [
                'skill(domain="b3_api", mode="status")',
            ],
        },

    },
}


def route(mode: str, **kwargs) -> dict:
    """
    Route a skill() call to the correct b3_api function.

    Uses inspect.signature to filter kwargs to only what the target function
    accepts. This means the dispatcher can evolve its unified param signature
    without breaking this domain. See cvm/__init__.py route() for full rationale.
    """
    if mode not in MANIFEST["modes"]:
        available = list(MANIFEST["modes"].keys())
        return {
            "status": "error",
            "error":  f"Unknown mode '{mode}' for domain 'b3_api'. Available: {available}",
        }

    import inspect
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {
            "status": "error",
            "domain": "b3_api",
            "mode":   mode,
            "error":  str(e),
        }
