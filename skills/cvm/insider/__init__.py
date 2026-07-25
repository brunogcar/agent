"""skills/cvm/insider/__init__.py -- Insider trading skill manifest + router.

Combines VLMO data (insider buy/sell disclosures) with bridge resolution.
Read-only — no sync. Calls data_sources.cvm.vlmo.query_engine directly.

Example:
  skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "insider",
    "description": (
        "Insider trading analysis from VLMO disclosures. "
        "history: recent insider transactions. "
        "by_role: grouped by role (director, officer, etc.). "
        "summary: net buy/sell per month. "
        "all: combined report."
    ),
    "source":  "vlmo.db (VLMO — Valores Mobiliários)",
    "storage": "read-only — no own database",
    "modes": {
        "history": {
            "description": "Recent insider transactions (newest-first). Returns: date, role, type (buy/sell), asset, qty, price, volume.",
            "include_in_all": False,
            "params": {
                "company": "str. Ticker, name, or CNPJ. Required.",
                "limit":   "int. Max results. Default: 50.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="insider", mode="history", params=\'{"company":"PETR4"}\')',
            ],
        },
        "by_role": {
            "description": "Insider transactions grouped by role (Tipo_Cargo). Shows total bought/sold per role.",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
                "limit":   "int. Max roles. Default: 50.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="insider", mode="by_role", params=\'{"company":"PETR4"}\')',
            ],
        },
        "summary": {
            "description": "Net buy/sell summary per month (last 24 months). Shows insider sentiment trend.",
            "include_in_all": True,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="insider", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch insider mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.insider.insider import history, by_role, summary

    dispatch = {
        "history": history,
        "by_role": by_role,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "insider",
                "mode": mode, "error": str(e)}
