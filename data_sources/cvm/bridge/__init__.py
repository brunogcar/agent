"""data_sources/cvm/bridge/__init__.py -- B3-CVM bridge sub-domain manifest + router.

The bridge resolves B3 trading tickers to CVM company identity (CNPJ, CD_CVM,
official names) using two already-synced data sources:

  1. b3/dividends  -- per-ticker API returns codeCVM (ticker -> cd_cvm)
  2. cvm/cad       -- company register (cd_cvm -> CNPJ + names + status + sector)

No bulk downloads, no instruments.db dependency, no ISIN ZIP.

Resolution chain:
  ticker -> dividends.company_info.code_cvm -> cad.cia_aberta (CD_CVM) -> bridge.db

The bridge.db is consumed by data_sources/cvm/_bridge.py (resolve_company),
which all CVM sub-domains (dfp, itr, fre, ipe) use to accept ticker input.

Storage: memory_db/cvm/bridge.db  (co-located with dfp.db, itr.db, cad.db)
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "bridge",
    "description": (
        "B3-CVM identity bridge. Resolves B3 tickers (PETR4) to CVM company "
        "identity (CNPJ, CD_CVM, names) via dividends API + CAD. "
        "No bulk downloads, no instruments dependency."
    ),
    "source":  "b3/dividends (codeCVM) + cvm/cad (CNPJ) -> bridge.db",
    "storage": "memory_db/cvm/bridge.db",
    "modes": {
        "sync": {
            "description": "Bridge one or more tickers: fetch dividends (if needed) + join CAD + upsert bridge.db.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Single ticker (e.g., PETR4). Ignored if tickers given.",
                "tickers": "list[str]. Multiple tickers. Takes precedence over ticker.",
                "force":   "bool. Re-fetch dividends + re-join CAD even if already bridged. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="bridge", mode="sync", params=\'{"ticker":"PETR4"}\')',
                'data_source(domain="cvm", sub_domain="bridge", mode="sync", params=\'{"tickers":["PETR4","VALE3","ITUB4"]}\')',
                'data_source(domain="cvm", sub_domain="bridge", mode="sync", params=\'{"ticker":"PETR4","force":true}\')',
            ],
        },
        "status": {
            "description": "Show bridge.db stats: total tickers, CNPJ coverage, last sync action.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="bridge", mode="status")',
            ],
        },
        "lookup": {
            "description": "Resolve a ticker, CNPJ, or CD_CVM to the full bridge identity record.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. B3 ticker (e.g., PETR4).",
                "cnpj":    "str. 14-digit CNPJ (formatted or numeric).",
                "cd_cvm":  "str. CVM code (e.g., 9512).",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="bridge", mode="lookup", params=\'{"ticker":"PETR4"}\')',
                'data_source(domain="cvm", sub_domain="bridge", mode="lookup", params=\'{"cd_cvm":"9512"}\')',
            ],
        },
        "resolve": {
            "description": "Fuzzy name search across trading_name + denom_social + denom_comerc.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment (>= 2 chars).",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="bridge", mode="resolve", params=\'{"query":"petro"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> object:
    """Route mode calls to the appropriate engine function."""
    if mode == "sync":
        from data_sources.cvm.bridge.sync_engine import sync
        return sync(**kwargs)

    if mode == "status":
        from data_sources.cvm.bridge.query_engine import status
        return status()

    if mode == "lookup":
        from data_sources.cvm.bridge.query_engine import lookup
        return lookup(**kwargs)

    if mode == "resolve":
        from data_sources.cvm.bridge.query_engine import resolve
        return resolve(**kwargs)

    # Unknown mode -- list available
    available = list(MANIFEST["modes"].keys())
    return {
        "status": "error",
        "error":  f"Unknown mode '{mode}'. Available: {available}",
        "available_modes": available,
    }
