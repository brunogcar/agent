"""skills/cvm/dividends/__init__.py -- Dividends skill manifest + router.

Combines B3 dividends (individual events) + DFP DVA (annual totals) +
CVM IPE (official filings).

Data sources used:
  - data_sources/b3/dividends  (cash_dividends table — individual events)
  - data_sources/cvm/dfp       (DVA 7.08.04.* — annual declared totals)
  - data_sources/cvm/ipe       (eventos table — keyword "dividendo")

No sync — read-only over already-synced data.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "dividends",
    "description": (
        "Dividend data combining 3 sources. "
        "history: individual events (B3). "
        "annual: declared totals (DFP DVA). "
        "payable: declared-but-unpaid (DFP BPP). "
        "announcements: official filings (IPE)."
    ),
    "source":  "dividends.db (B3) + dfp.db (DVA 7.08.04.*) + ipe.db (filings)",
    "storage": "read-only — no own database",
    "modes": {
        "history": {
            "description": "Individual dividend events (rate, dates, label Dividendo/JCP) from B3.",
            "include_in_all": False,
            "params": {
                "company": "str. B3 ticker (PETR4). Required.",
                "limit":   "int. Max events. Default: 50.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="dividends", mode="history", params=\'{"company":"PETR4"}\')',
            ],
        },
        "annual": {
            "description": "Annual declared dividend totals (Dividendos + JCP) from DFP DVA 7.08.04.*.",
            "include_in_all": False,
            "params": {
                "company": "str. B3 ticker, name, or CNPJ. Required.",
                "periods": "int. Number of fiscal years. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="dividends", mode="annual", params=\'{"company":"PETR4"}\')',
            ],
        },
        "payable": {
            "description": "Dividends declared but not yet paid (DFP BPP 2.01.05.02.01).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
                "periods": "int. Number of fiscal years. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="dividends", mode="payable", params=\'{"company":"VALE3"}\')',
            ],
        },
        "announcements": {
            "description": "Official CVM IPE filings related to dividends (keyword search).",
            "include_in_all": False,
            "params": {
                "company": "str. Company name, CNPJ, or ticker (via bridge). Empty = all.",
                "limit":   "int. Max results. Default: 20.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="dividends", mode="announcements", params=\'{"company":"PETR4"}\')',
            ],
        },
        "summary": {
            "description": "Combined: recent events + annual trend + last payable.",
            "include_in_all": True,
            "params": {
                "company": "str. Required (ticker preferred).",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="dividends", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch dividends mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.dividends.dividends import (
        history, annual, payable, announcements, summary,
    )

    dispatch = {
        "history": history,
        "annual": annual,
        "payable": payable,
        "announcements": announcements,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "dividends",
                "mode": mode, "error": str(e)}
