"""
skills/cvm/cvm_dividends/__init__.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_dividends\__init__.py

Routes skill(domain="cvm", sub_domain="cvm_dividends", mode=...) calls.

ARCHITECTURE CHANGE (v2):
  Old: imported annual(), declared(), cash_paid(), db_status() as separate functions
  New: single cvm_dividends(ticker, mode, periods) dispatcher handles all modes
  Reason: bridge-aware resolution + consistent return shape across all modes.

MODE -> dispatcher mapping:
  "annual"    -> cvm_dividends(mode="annual")
  "declared"  -> cvm_dividends(mode="declared")
  "cash_paid" -> cvm_dividends(mode="cash_paid")
  "status"    -> cvm_dividends(mode="status")  [default, include_in_all]

All modes accept: ticker (B3 ticker, name fragment, or CNPJ), periods (int).
"""

from __future__ import annotations

import inspect
from skills.cvm.cvm_dividends.cvm_dividends import cvm_dividends

MANIFEST = {
    "sub_domain":  "cvm_dividends",
    "description": (
        "Dividend and JCP data from rapina.db. "
        "Three sources: DVA (annual declared), BPP (payable balance), DFC (cash paid). "
        "Accepts B3 ticker (requires bridge sync), company name, or CNPJ."
    ),
    "source":  "rapina.db -- DVA 7.08.04.*, BPP 2.01.05.02.*, DFC 6.03.*",
    "storage": "memory_db/cvm/rapina.db (read-only)",

    "modes": {
        "status": {
            "description":    "Quick summary: latest DVA + DFC + BPP for a company.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. B3 ticker (PETR4), name fragment (PETROBRAS), or CNPJ. Required.",
                "periods": "int. Ignored for status mode.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="status", params=\'{"ticker":"PETR4"}\')',
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="status", params=\'{"ticker":"PETROBRAS"}\')',
            ],
        },
        "annual": {
            "description":    "Annual dividends declared from DVA (7.08.04.*). ~10K companies, 2009-present.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. B3 ticker, name fragment, or CNPJ. Required.",
                "periods": "int. Number of years to return. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="annual", params=\'{"ticker":"PETR4"}\')',
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="annual", params=\'{"ticker":"VALE","periods":3}\')',
            ],
        },
        "declared": {
            "description":    "Dividends payable on balance sheet (BPP 2.01.05.02.01). Quarterly snapshot.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Required.",
                "periods": "int. Number of periods. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="declared", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "cash_paid": {
            "description":    "Cash actually paid for dividends/JCP from DFC (6.03.05/06). Quarterly cumulative.",
            "include_in_all": False,
            "params": {
                "ticker":  "str. Required.",
                "periods": "int. Number of periods. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_dividends", mode="cash_paid", params=\'{"ticker":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """
    Dispatch cvm_dividends mode call.

    All modes route to cvm_dividends(ticker=..., mode=..., periods=...).
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

    # Only pass params the dispatcher accepts
    sig      = inspect.signature(cvm_dividends)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    filtered["mode"] = mode

    try:
        return cvm_dividends(**filtered)
    except Exception as e:
        return {
            "status":     "error",
            "sub_domain": "cvm_dividends",
            "mode":       mode,
            "error":      str(e),
        }
