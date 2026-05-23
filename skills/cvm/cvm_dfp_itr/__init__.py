"""
skills/cvm/cvm_dfp_itr/__init__.py -- CVM API sub-domain manifest.

Routes skill(domain="cvm", sub_domain="cvm_dfp_itr", mode=...) calls.
Reads from dfp_itr.db (built by dfp_itr_sync).
"""

from __future__ import annotations
import inspect
from skills.cvm.cvm_dfp_itr.cvm_dfp_itr import (
    completo_anual, completo_trim,
    resumo_anual,   resumo_trim,
    search_companies, db_status,
)

MANIFEST = {
    "sub_domain":  "cvm_dfp_itr",
    "description": "CVM financial statements from dfp_itr.db. Annual and quarterly DFP/ITR for ~700 listed companies.",
    "source":      "dfp_itr.db (dfp_itr_sync) -- update: dfp_itr_sync atualizar --all",
    "storage":     "memory_db/cvm/dfp_itr.db (read-only, 1.5GB)",

    "modes": {
        "completo_anual": {
            "fn":             completo_anual,
            "description":    "All account codes, annual data (meses=12), consolidated.",
            "include_in_all": False,
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Years e.g. [2023,2024]. Default: last 5.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
                "limit_years": "int. Max years. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="completo_anual", params=\'{"company":"PETROBRAS"}\')',
            ],
        },
        "completo_trim": {
            "fn":             completo_trim,
            "description":    "All account codes, quarterly data (meses=3/6/9), consolidated.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 3.",
                "consolidado": "int. Default: 1.",
                "limit_years": "int. Default: 3.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="completo_trim", params=\'{"company":"PETROBRAS"}\')',
            ],
        },
        "resumo_anual": {
            "fn":             resumo_anual,
            "description":    "Key metrics only, annual. Revenue, EBIT, net income, assets, equity, cash flows.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 10.",
                "consolidado": "int. Default: 1.",
                "limit_years": "int. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="resumo_anual", params=\'{"company":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="resumo_anual", params=\'{"company":"VALE","limit_years":5}\')',
            ],
        },
        "resumo_trim": {
            "fn":             resumo_trim,
            "description":    "Key metrics only, quarterly.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 4.",
                "consolidado": "int. Default: 1.",
                "limit_years": "int. Default: 4.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="resumo_trim", params=\'{"company":"PETROBRAS"}\')',
            ],
        },
        "search": {
            "fn":             search_companies,
            "description":    "Search companies by name or CNPJ in dfp_itr.db.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment or partial CNPJ. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="search", params=\'{"query":"PETRO"}\')',
            ],
        },
        "status": {
            "fn":             db_status,
            "description":    "Show dfp_itr.db info: size, rows, date range.",
            "include_in_all": True,
            "params":         {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dfp_itr", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    if not mode:
        return {"status": "error", "error": f"mode is required for cvm_dfp_itr. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for cvm_dfp_itr. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "cvm_dfp_itr", "mode": mode, "error": str(e)}
