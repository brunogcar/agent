"""
skills/cvm/cvm_dfp_itr/__init__.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_dfp_itr\__init__.py
Routes skill(domain="cvm", sub_domain="cvm_dfp_itr", mode=...) calls.

Modes:
  sync           -- download CVM DFP/ITR ZIPs and populate dfp_itr.db
  status         -- show db stats (row counts, date range, synced years)
  query          -- alias for completo_anual (full annual statements)
  completo_anual -- all account codes, meses=12
  completo_trim  -- all account codes, meses=3/6/9
  resumo_anual   -- key metrics only, meses=12
  resumo_trim    -- key metrics only, meses=3/6/9
  search         -- search companies by name fragment
"""
from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "cvm_dfp_itr",
    "description": (
        "CVM DFP/ITR financial statements (BPA, BPP, DRE, DFC, DVA). "
        "~11K companies, quarterly + annual, 2009-present. "
        "Accepts B3 ticker (bridge), name fragment, or CNPJ."
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
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="sync", params=\'{"form": "ITR"}\')',
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
            "description": "Full annual statements for a company (alias for completo_anual).",
            "include_in_all": False,
            "params": {
                "company":     "str. B3 ticker, name fragment, or CNPJ. Required.",
                "grupo":       "str. BPA|BPP|DRE|DFC_MI|DVA|DMPL. Optional.",
                "codigo":      "str. Account code prefix e.g. '3.04'. Optional.",
                "anos":        "list[int]. Specific years. Default: last 3.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="query", params=\'{"company": "PETR4", "grupo": "DVA"}\')',
            ],
        },
        "completo_anual": {
            "description": "Full annual statements with all account codes (DFP, meses=12).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.", "grupo": "str. Optional.",
                "anos": "list[int].", "consolidado": "int.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="completo_anual", params=\'{"company": "VALE3", "anos":[2023,2024]}\')',
            ],
        },
        "completo_trim": {
            "description": "Full quarterly statements (ITR, meses=3/6/9).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.", "grupo": "str. Optional.",
                "anos": "list[int].", "consolidado": "int.",
            },
            "examples": [],
        },
        "resumo_anual": {
            "description": "Summary annual statements (key accounts: revenue, EBITDA, profit, equity).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.", "anos": "list[int].", "consolidado": "int.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="resumo_anual", params=\'{"company": "ITUB4"}\')',
            ],
        },
        "resumo_trim": {
            "description": "Summary quarterly statements.",
            "include_in_all": False,
            "params": {
                "company": "str. Required.", "anos": "list[int].", "consolidado": "int.",
            },
            "examples": [],
        },
        "search": {
            "description": "Search companies by name fragment. Returns list of matches with CNPJ.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="search", params=\'{"query": "PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """
    Dispatch cvm_dfp_itr mode call.
    mode="query" is an alias for completo_anual.
    All query modes accept 'company' (B3 ticker via bridge, name, or CNPJ).
    """
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        # ── sync ──────────────────────────────────────────────────────────────
        if mode == "sync":
            from skills.cvm.cvm_dfp_itr_sync import sync as _sync
            sig      = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        # ── status ────────────────────────────────────────────────────────────
        elif mode == "status":
            try:
                from skills.cvm.cvm_dfp_itr_sync import status as _status
                return _status()
            except ImportError:
                from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import db_status
                return db_status()

        # ── query functions ───────────────────────────────────────────────────
        else:
            from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import (
                completo_anual, completo_trim,
                resumo_anual,   resumo_trim,
                search_companies,
            )
            fn_map = {
                "query":          completo_anual,   # convenience alias
                "completo_anual": completo_anual,
                "completo_trim":  completo_trim,
                "resumo_anual":   resumo_anual,
                "resumo_trim":    resumo_trim,
                "search":         search_companies,
            }
            fn = fn_map.get(mode)
            if fn is None:
                return {
                    "status": "error",
                    "error": f"Mode '{mode}' not implemented. Available: {list(fn_map.keys())}",
                }
            sig = inspect.signature(fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return fn(**filtered)

    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "cvm_dfp_itr",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }