"""
skills/cvm/cvm_dividends/__init__.py -- CVM Dividends sub-domain manifest.

Routes skill(domain="cvm", sub_domain="cvm_dividends", mode=...) calls.
"""

from __future__ import annotations
import inspect
from skills.cvm.cvm_dividends.cvm_dividends import (
    annual, declared, cash_paid, db_status,
)

MANIFEST = {
    "sub_domain":  "cvm_dividends",
    "description": "Dividend and JCP data from rapina.db. Three sources: DVA (distributed, ~10K companies), BPP (declared/payable), DFC (cash paid).",
    "source":      "rapina.db contas table -- DVA 7.08.04.*, BPP 2.01.05.02.*, DFC 6.03.*",
    "storage":     "memory_db/cvm/rapina.db (read-only)",

    "modes": {
        "annual": {
            "fn":             annual,
            "description":    "Annual dividends + JCP from DVA. Primary source, ~10K companies, 2009-present.",
            "include_in_all": False,
            "params": {
                "company":          "str. Company name, partial name, or CNPJ. Required.",
                "anos":             "list[int]. Specific years e.g. [2022,2023]. Default: last 10.",
                "consolidado":      "int. 1=consolidated (default), 0=individual.",
                "limit_years":      "int. Max years. Default: 10.",
                "include_retained": "bool. Include retained earnings (7.08.04.01). Default: False.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="annual", params=\'{"company":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="annual", params=\'{"company":"VALE","limit_years":5}\')',
            ],
        },
        "declared": {
            "fn":             declared,
            "description":    "Dividends declared but not yet paid (BPP). Shows payables + reserves at balance sheet date.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 5.",
                "consolidado": "int. Default: 1.",
                "limit_years": "int. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="declared", params=\'{"company":"PETROBRAS"}\')',
            ],
        },
        "cash_paid": {
            "fn":             cash_paid,
            "description":    "Actual cash paid for dividends/JCP from DFC. Coverage varies by company.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "anos":        "list[int]. Default: last 10.",
                "consolidado": "int. Default: 1.",
                "limit_years": "int. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="cash_paid", params=\'{"company":"PETROBRAS"}\')',
            ],
        },
        "status": {
            "fn":             db_status,
            "description":    "Show rapina.db dividend data coverage stats.",
            "include_in_all": True,
            "params":         {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    if not mode:
        return {"status": "error",
                "error": f"mode required for cvm_dividends. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for cvm_dividends. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "cvm_dividends", "mode": mode, "error": str(e)}
