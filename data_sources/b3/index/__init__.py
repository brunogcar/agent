"""data_sources/b3/index/__init__.py -- B3 index sub-domain manifest + router.

B3 indexProxy: index composition (constituents + weights).
26 indices catalogued, 5 active for sync (IBOV, SMLL, BDRX, IFIX, IDIV).

Modes:
  sync_index  -- sync a single index (params: index_code)
  sync_all    -- sync all active indices
  index       -- get latest composition (params: index_code)
  search      -- search catalog (params: query)
  summary     -- overview of all synced indices
  history     -- historical compositions (params: index_code, days)
  ticker      -- find which indices a ticker belongs to (params: ticker)
  status      -- database stats
"""
from __future__ import annotations

from typing import Any

MANIFEST = {
    "sub_domain":  "index",
    "description": (
        "B3 index composition (constituents + weights). "
        "26 indices catalogued, 5 active: IBOV, SMLL, BDRX, IFIX, IDIV. "
        "Historical compositions preserved for tracking changes."
    ),
    "source":  "https://sistemaswebb3-listados.b3.com.br/indexProxy",
    "storage": "memory_db/b3/index.db",
    "modes": {
        "sync_index":  {"description": "Sync a single index", "include_in_all": False},
        "sync_all":    {"description": "Sync all active indices", "include_in_all": True},
        "index":       {"description": "Get latest composition", "include_in_all": True},
        "search":      {"description": "Search catalog", "include_in_all": True},
        "summary":     {"description": "Overview of all indices", "include_in_all": True},
        "history":     {"description": "Historical compositions", "include_in_all": False},
        "ticker":      {"description": "Find indices for a ticker", "include_in_all": True},
        "status":      {"description": "Database stats", "include_in_all": False},
    },
}


def route(mode: str = "", **kwargs: Any) -> Any:
    """Route data_source(domain='b3', sub_domain='index', mode=...) calls."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}

    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_index":
            from data_sources.b3.index.sync_engine import sync_index
            index_code = kwargs.get("index_code", "")
            if not index_code:
                return {"status": "error", "error": "index_code is required"}
            return sync_index(index_code, force=kwargs.get("force", False))

        elif mode == "sync_all":
            from data_sources.b3.index.sync_engine import sync_all
            return sync_all(force=kwargs.get("force", False))

        elif mode == "index":
            from data_sources.b3.index.query_engine import index as query_index
            return query_index(kwargs.get("index_code", ""))

        elif mode == "search":
            from data_sources.b3.index.query_engine import search
            return search(kwargs.get("query", ""))

        elif mode == "summary":
            from data_sources.b3.index.query_engine import summary
            return summary()

        elif mode == "history":
            from data_sources.b3.index.query_engine import history
            return history(kwargs.get("index_code", ""), int(kwargs.get("days", 90)))

        elif mode == "ticker":
            from data_sources.b3.index.query_engine import ticker_search
            return ticker_search(kwargs.get("ticker", ""))

        elif mode == "status":
            from data_sources.b3.index.status_reporter import status
            return status()

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented"}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
