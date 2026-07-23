"""
skills/b3/b3_cvm/__init__.py -- B3-CVM bridge sub-domain manifest and router.

Deploy to: D:\mcp\agent\skills\b3\b3_cvm\__init__.py

DECISION: single sub_domain "b3_cvm" under the b3/ domain.
The bridge does not fetch prices (that is b3_api's job).
It only resolves company identity. Clean separation of concerns.

The dispatcher (skills/dispatcher.py) auto-discovers this domain because:
  1. skills/b3/__init__.py defines has_sub_domains=True and _discover_sub_domains()
  2. This __init__.py defines MANIFEST["domain"] and route()
  3. route() lazy-imports b3_cvm.py so server startup is not slowed down
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

MANIFEST = {
    "domain": "b3_cvm",
    "description": (
        "Company identity bridge: maps B3 tickers to CVM CD_CVM codes, "
        "CNPJs, and dfp_itr.db empresa IDs. "
        "Sync once per week. Lookup is instant (SQLite only, no network)."
    ),
    "modes": {
        "sync": {
            "description": (
                "Download B3 ISIN ZIP + CVM cad_cia_aberta.csv and build "
                "bridge.db. Run once per week. Takes ~10-15s."
            ),
            "include_in_all": False,  # hits network + writes disk -- explicit only
        },
        "status": {
            "description": "Show bridge.db sync status and coverage statistics.",
            "include_in_all": True,
        },
        "lookup": {
            "description": (
                "Resolve company by ticker, CNPJ, or CD_CVM. "
                "Returns: cnpj, cd_cvm, denom_social, denom_comerc, "
                "tickers (all B3 codes), dfp_itr_ids (list of ints for dfp_itr queries)."
            ),
            "include_in_all": False,
        },
        "resolve": {
            "description": "Fuzzy name search. Returns list of matching companies.",
            "include_in_all": False,
        },
        "tickers": {
            "description": "List all B3 tickers for a company (name or CNPJ).",
            "include_in_all": False,
        },
    },
}


def route(sub_domain: str, mode: str, **kwargs: Any) -> Any:
    """
    Dispatch b3_cvm mode call. Lazy-imports b3_cvm.py.

    DECISION: Lazy import so that httpx and sqlite3 are not imported at
    server startup (same pattern as all other skills). The MCP server
    must respond to ListToolsRequest quickly; heavy imports block that.
    """
    mod = importlib.import_module("skills.b3.b3_cvm.b3_cvm")

    dispatch = {
        "sync":    mod.mode_sync,
        "status":  mod.mode_status,
        "lookup":  mod.mode_lookup,
        "resolve": mod.mode_resolve,
        "tickers": mod.mode_tickers,
    }

    fn = dispatch.get(mode)
    if fn is None:
        return {
            "status": "error",
            "error": f"Unknown mode '{mode}' for b3_cvm. Available: {list(dispatch)}",
        }

    # Filter kwargs to only what the function signature accepts
    sig   = inspect.signature(fn)
    valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**valid)
