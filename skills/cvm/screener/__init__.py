"""skills/cvm/screener/__init__.py -- Sector screener skill manifest + router.

Lists companies in a sector and computes sector medians (P/L, ROE, EV/EBITDA)
so the LLM can ask "is SUZB3 cheap vs its sector?".

NO SYNC — read-only, like all CVM skills. Calls CAD + bridge + valuation
internally.

Example:
  skill(domain="cvm", sub_domain="screener", mode="sector",
        params='{"setor":"Papel e Celulose"}')
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "screener",
    "description": (
        "Sector screener. List companies in a sector + compute median P/L, ROE, "
        "EV/EBITDA. compare: is a ticker cheap vs its sector?"
    ),
    "source":  "calls CAD + bridge + valuation skills internally",
    "storage": "read-only — no own database",
    "modes": {
        "sector": {
            "description": "List all active companies in a sector with their valuation ratios. Returns sector medians for P/L, ROE, EV/EBITDA.",
            "include_in_all": True,
            "params": {
                "setor":  "str. Sector name fragment (e.g. 'Papel', 'Energia', 'Bancos'). Required.",
                "limit":  "int. Max companies to fetch. Default: 20.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="screener", mode="sector", params=\'{"setor":"Papel e Celulose"}\')',
            ],
        },
        "compare": {
            "description": "Compare a ticker against its sector medians. Resolves the ticker's sector, fetches all sector peers, computes medians, returns the ticker's values vs sector medians.",
            "include_in_all": False,
            "params": {
                "company": "str. B3 ticker (e.g. 'SUZB3'). Required.",
                "limit":   "int. Max peers to fetch for median. Default: 20.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="screener", mode="compare", params=\'{"company":"SUZB3"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch screener mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.screener.screener import sector, compare

    dispatch = {
        "sector":  sector,
        "compare": compare,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "screener",
                "mode": mode, "error": str(e)}
