"""
skills/cvm/cvm_dfp_itr/__init__.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_dfp_itr\__init__.py

Routes skill(domain="cvm", sub_domain="cvm_dfp_itr", mode=...) calls.

RENAMED FROM: skills/cvm/cvm_api/__init__.py
sync mode now uses cvm_dfp_itr_sync.py (our own downloader, replaces rapinav2).

Modes:
  sync    -- download CVM DFP/ITR ZIPs and populate dfp_itr.db
  status  -- show db stats (row counts, date range, synced years)
  query   -- query financial data for a company (existing cvm_api logic)
"""

from __future__ import annotations

import inspect


MANIFEST = {
    "sub_domain":  "cvm_dfp_itr",
    "description": (
        "CVM DFP/ITR financial statements (BPA, BPP, DRE, DFC, DVA). "
        "~10K companies, quarterly + annual, 2010-present. "
        "Accepts B3 ticker (bridge), name, or CNPJ."
    ),
    "source":  "dados.cvm.gov.br DFP + ITR ZIPs -> dfp_itr.db",
    "storage": "memory_db/cvm/dfp_itr.db",

    "modes": {
        "sync": {
            "description": (
                "Download CVM DFP/ITR ZIPs and populate dfp_itr.db. "
                "Default: current + prior year (~30s). full_history=true: all years (~10 min)."
            ),
            "include_in_all": False,
            "params": {
                "form":         "str. 'DFP' (annual) or 'ITR' (quarterly). Default: 'DFP'.",
                "years":        "list[int]. Specific years. Default: current + prior.",
                "full_history": "bool. All years from 2010. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="sync")',
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="sync", params=\'{"form":"ITR"}\')',
            ],
        },
        "status": {
            "description": "Show dfp_itr.db stats: empresas, contas, date range, synced years.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="status")',
            ],
        },
        "query": {
            "description": "Query financial statements for a company by code/grupo/year.",
            "include_in_all": False,
            "params": {
                "company":     "str. B3 ticker, name fragment, or CNPJ. Required.",
                "grupo":       "str. BPA|BPP|DRE|DFC|DVA|DMPL. Optional.",
                "codigo":      "str. Account code prefix e.g. '3.04'. Optional.",
                "anos":        "list[int]. Specific years. Default: last 3.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="query", params=\'{"company":"PETR4","grupo":"DVA"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch cvm_dfp_itr mode call. Lazy imports to keep startup fast."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    # Lazy import -- cvm_dfp_itr.py may not exist yet if running after rename
    # We also import sync separately since it lives in cvm_dfp_itr_sync.py
    try:
        if mode == "sync":
            from skills.cvm.cvm_dfp_itr_sync import sync as _sync_fn
            sig      = inspect.signature(_sync_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync_fn(**filtered)

        elif mode == "status":
            # Try dfp_itr_sync status first (shows sync_state table)
            try:
                from skills.cvm.cvm_dfp_itr_sync import status as _status_fn
                return _status_fn()
            except ImportError:
                from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import db_status
                return db_status()

        elif mode == "query":
            from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import mode_query
            sig      = inspect.signature(mode_query)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return mode_query(**filtered)

    except Exception as e:
        return {"status": "error", "sub_domain": "cvm_dfp_itr",
                "mode": mode, "error": str(e)}

    return {"status": "error", "error": f"Unhandled mode '{mode}'"}
