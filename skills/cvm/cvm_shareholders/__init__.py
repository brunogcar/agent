"""
skills/cvm/cvm_shareholders/__init__.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_shareholders\__init__.py

Routes skill(domain="cvm", sub_domain="cvm_shareholders", mode=...) calls.

ARCHITECTURE CHANGE (v2):
  Old: imported equity_structure(), minority(), db_status() as separate functions
  New: single cvm_shareholders(ticker, mode, periods) dispatcher handles all modes
  Reason: bridge-aware resolution + consistent return shape across all modes.

MODE -> dispatcher mapping:
  "status"           -> cvm_shareholders(mode="status")
  "equity_structure" -> cvm_shareholders(mode="equity_structure")
  "minority"         -> cvm_shareholders(mode="minority")

All modes accept: ticker (B3 ticker, name fragment, or CNPJ), periods (int).
"""

from __future__ import annotations

import inspect
from skills.cvm.cvm_shareholders.cvm_shareholders import cvm_shareholders

MANIFEST = {
    "sub_domain":  "cvm_shareholders",
    "description": (
        "Shareholder equity structure from dfp_itr.db BPP 2.03.*. "
        "Capital, reserves, retained earnings, minority interest. "
        "Accepts B3 ticker (requires bridge sync), company name, or CNPJ."
    ),
    "source":  "dfp_itr.db -- BPP 2.03.* (Patrimonio Liquido)",
    "storage": "memory_db/cvm/dfp_itr.db (read-only)",

    "modes": {
        "status": {
            "description":    "Latest PL snapshot: total equity + key components.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. B3 ticker (VALE3), name fragment (VALE), or CNPJ. Required.",
                "periods": "int. Ignored for status mode.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="status", params=\'{"ticker":"VALE3"}\')',
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="status", params=\'{"ticker":"PETROBRAS"}\')',
            ],
        },
        "equity_structure": {
            "description":    "Full PL breakdown per period: capital, reserves, retained, minority (BPP 2.03.*).",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Required.",
                "periods": "int. Number of periods. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="equity_structure", params=\'{"ticker":"PETR4"}\')',
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="equity_structure", params=\'{"ticker":"VALE","periods":3}\')',
            ],
        },
        "minority": {
            "description":    "Minority interest (2.03.09) vs total equity trend. Shows % of PL per period.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Required.",
                "periods": "int. Number of periods. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="minority", params=\'{"ticker":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_shareholders", mode="minority", params=\'{"ticker":"ITUB4","periods":3}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """
    Dispatch cvm_shareholders mode call.

    All modes route to cvm_shareholders(ticker=..., mode=..., periods=...).
    The 'company' param from old callers is aliased to 'ticker' for compatibility.
    """
    if not mode:
        return {
            "status": "error",
            "error":  f"mode required. Options: {list(MANIFEST['modes'].keys())}",
        }
    if mode not in MANIFEST["modes"]:
        return {
            "status": "error",
            "error":  f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}",
        }

    # Backward-compat: old callers used 'company' param, new uses 'ticker'
    if "company" in kwargs and "ticker" not in kwargs:
        kwargs["ticker"] = kwargs.pop("company")

    sig      = inspect.signature(cvm_shareholders)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    filtered["mode"] = mode

    try:
        return cvm_shareholders(**filtered)
    except Exception as e:
        return {
            "status":     "error",
            "sub_domain": "cvm_shareholders",
            "mode":       mode,
            "error":      str(e),
        }
