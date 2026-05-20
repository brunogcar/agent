"""
skills/b3/b3_cvm/__init__.py -- B3-CVM identity bridge domain manifest.

=== PURPOSE ===
This domain's ONLY job is resolving company identity across three systems
that each use a different primary key:

  B3 (trading):   ticker  (PETR4, VALE3, ITUB4...)
  CVM (filings):  CD_CVM  (integer, e.g. 9512 for Petrobras)
  rapina.db:      empresa.id (internal integer, multiple per company/year)

The bridge.db file (memory_db/cvm/bridge.db) is the single source of truth.
It is populated by mode="sync" and then read-only by all other skills.

=== HOW THE DISPATCHER USES THIS ===
skills/dispatcher.py calls:
  1. MANIFEST to list available modes
  2. route(sub_domain, mode, params) to dispatch calls
  3. inspect.signature filtering to pass only valid params

The dispatcher auto-discovers this domain because this __init__.py
defines MANIFEST and route() following the exact pattern used by
skills/b3/b3_api/__init__.py and skills/cvm/cvm_api/__init__.py.

=== DECISION: single sub_domain "b3_cvm" ===
Unlike b3/ (which has b3_api as sub_domain) or cvm/ (which has cvm_api,
cvm_register, cvm_dividends, cvm_shareholders), the bridge is a single
focused skill. It does NOT try to also do B3 or CVM data fetching --
those remain in their respective skills. The bridge is an index, not a store.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

# ── MANIFEST ──────────────────────────────────────────────────────────────────
# Tells the dispatcher what this domain can do.
# Each mode is what the LLM sees when it calls skill(domain="b3_cvm", mode=X).
#
# DECISION: include_in_all=False for sync -- we do NOT want sync() running
# automatically when the agent calls skill(domain="b3_cvm", mode="all").
# Sync hits the network and writes to disk; it should be explicit.

MANIFEST = {
    "domain": "b3_cvm",
    "description": (
        "Company identity bridge: maps B3 tickers to CVM CD_CVM codes, "
        "CNPJs, and rapina.db empresa IDs. Required for cross-skill lookups "
        "(e.g. getting dividends by ticker). Sync once per week; lookup is instant."
    ),
    "modes": {
        "sync": {
            "description": (
                "Download B3 ISIN file + CVM cad_cia_aberta.csv and build "
                "the identity bridge table in bridge.db. Run once per week "
                "or when new companies are listed. Takes ~10-15 seconds."
            ),
            "params": {},
            "include_in_all": False,   # explicit only -- hits network + writes disk
        },
        "status": {
            "description": (
                "Show bridge.db sync status: last sync date, row count, "
                "coverage statistics. Quick health check."
            ),
            "params": {},
            "include_in_all": True,
        },
        "lookup": {
            "description": (
                "Resolve a company by ticker, CNPJ, or CD_CVM to its full "
                "identity record: {ticker, isin, cnpj, cd_cvm, denom_social, "
                "denom_comerc, sit, rapina_ids}. Use before calling cvm_dividends "
                "or cvm_shareholders with a ticker."
            ),
            "params": {
                "ticker":  "B3 ticker code, e.g. 'PETR4' (optional)",
                "cnpj":    "14-digit CNPJ, e.g. '33000167000101' (optional)",
                "cd_cvm":  "CVM integer code, e.g. 9512 (optional)",
            },
            "include_in_all": False,
        },
        "resolve": {
            "description": (
                "Fuzzy search by company name. Returns list of matching "
                "company_map rows. Useful when you only have a name fragment "
                "like 'PETROBRAS' or 'ITAU'."
            ),
            "params": {
                "query": "Name fragment to search (case-insensitive)",
            },
            "include_in_all": False,
        },
        "tickers": {
            "description": (
                "List all tickers in bridge.db for a given company name or CNPJ. "
                "Useful to discover that PETR3/PETR4/PETR4F all belong to the same CNPJ."
            ),
            "params": {
                "query": "Name fragment or CNPJ to look up",
            },
            "include_in_all": False,
        },
    },
}


# ── route() ───────────────────────────────────────────────────────────────────
# Called by skills/dispatcher.py. Lazy-imports the implementation module
# so that httpx/sqlite3 are not imported at server startup time.
# This is the same lazy-import pattern used by all other skill domains.

def route(sub_domain: str, mode: str, params: dict) -> Any:
    """
    Dispatch a b3_cvm skill call.

    sub_domain is always "b3_cvm" for this domain (single sub-domain).
    mode is one of: sync | status | lookup | resolve | tickers
    params is a dict of keyword arguments matching the mode's params.
    """
    # DECISION: lazy import -- b3_cvm.py imports httpx and sqlite3.
    # These are fine at call time but would slow server startup if imported
    # at module level (same reason all skills use lazy imports).
    mod = importlib.import_module("skills.b3.b3_cvm.b3_cvm")

    # Dispatch table: mode -> function in b3_cvm.py
    dispatch = {
        "sync":    mod.mode_sync,
        "status":  mod.mode_status,
        "lookup":  mod.mode_lookup,
        "resolve": mod.mode_resolve,
        "tickers": mod.mode_tickers,
    }

    fn = dispatch.get(mode)
    if fn is None:
        available = list(dispatch.keys())
        return {
            "status": "error",
            "error": f"Unknown mode '{mode}' for b3_cvm. Available: {available}",
        }

    # Filter params to only those the function actually accepts
    # (same pattern used in other skill __init__.py files)
    sig    = inspect.signature(fn)
    valid  = {k: v for k, v in params.items() if k in sig.parameters}
    return fn(**valid)
