"""
skills/cvm/cvm_shareholders/__init__.py -- CVM Shareholders sub-domain manifest.

Routes skill(domain="cvm", sub_domain="cvm_shareholders", mode=...) calls.
"""

from __future__ import annotations
import inspect
from skills.cvm.cvm_shareholders.cvm_shareholders import (
    equity_structure, minority, db_status,
)

MANIFEST = {
    "sub_domain":  "cvm_shareholders",
    "description": "Shareholder equity structure from rapina.db BPP 2.03.*. Capital, reserves, retained earnings, minority interest. ~10K companies, 2009-present.",
    "source":      "rapina.db contas table -- BPP 2.03.* (Patrimônio Líquido)",
    "storage":     "memory_db/cvm/rapina.db (read-only)",

    "modes": {
        "equity_structure": {
            "fn":             equity_structure,
            "description":    "Full equity breakdown: capital, reserves, retained earnings, minority interest per period.",
            "include_in_all": False,
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Specific years e.g. [2022,2023]. Default: last 10.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
                "limit_years": "int. Max years. Default: 10.",
                "summary":     "bool. Top-level codes only (2.03, 2.03.01, 2.03.04, 2.03.09). Default: False.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="equity_structure", params=\'{"company":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="equity_structure", params=\'{"company":"VALE","summary":true,"limit_years":5}\')',
            ],
        },
        "minority": {
            "fn":             minority,
            "description":    "Minority interest (2.03.09) vs total equity (2.03). Computes minority % per period.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 10.",
                "consolidado": "int. Default: 1 (individual statements have no minority interest).",
                "limit_years": "int. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="minority", params=\'{"company":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="minority", params=\'{"company":"ITAU UNIBANCO","limit_years":5}\')',
            ],
        },
        "status": {
            "fn":             db_status,
            "description":    "Show rapina.db shareholder data coverage: companies with equity, minority interest stats.",
            "include_in_all": True,
            "params":         {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    if not mode:
        return {"status": "error",
                "error": f"mode required for cvm_shareholders. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for cvm_shareholders. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "cvm_shareholders", "mode": mode, "error": str(e)}
