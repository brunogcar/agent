"""skills/cvm/financials/__init__.py -- Financials skill manifest + router.

Combines DFP (annual) + ITR (quarterly cumulative) + DVA to produce
rapina-style financial summaries with standalone quarters + ratios.

Data sources used:
  - data_sources/cvm/dfp  (annual financial statements — meses=12)
  - data_sources/cvm/itr  (quarterly cumulative — meses=3/6/9)
  - data_sources/cvm/bridge (ticker → CNPJ → empresa_ids)

No sync — read-only over already-synced data.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "financials",
    "description": (
        "Financial statements + ratios. "
        "quarterly: standalone quarters derived from ITR cumulative + DFP (default). "
        "annual: annual summary from DFP. "
        "complete: full statements by grupo + key account codes. "
        "summary: combined latest annual + quarterly."
    ),
    "source":  "dfp.db (annual) + itr.db (quarterly cumulative) + dfp.db DVA (proventos)",
    "storage": "read-only — no own database",
    "modes": {
        "quarterly": {
            "description": "Standalone quarterly summary + ratios (default 8 quarters). Derives Q1-Q4 from ITR cumulative + DFP annual.",
            "include_in_all": False,
            "params": {
                "company":     "str. B3 ticker (PETR4), name, or CNPJ. Required.",
                "periods":     "int. Number of quarters. Default: 8.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="financials", mode="quarterly", params=\'{"company":"PETR4"}\')',
                'skill(domain="cvm", sub_domain="financials", mode="quarterly", params=\'{"company":"VALE3","periods":12}\')',
            ],
        },
        "annual": {
            "description": "Annual summary + ratios from DFP (default 5 years). Includes EBITDA, margins, ROA/ROE, debt ratios, payout.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "periods":     "int. Number of years. Default: 5.",
                "consolidado": "int. Default: 1.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="financials", mode="annual", params=\'{"company":"PETR4"}\')',
            ],
        },
        "complete": {
            "description": "Full statements by grupo + key account codes (not all 497). Default period=quarterly.",
            "include_in_all": False,
            "params": {
                "company":     "str. Required.",
                "period":      "str. 'quarterly' (default) or 'annual'.",
                "grupo":       "str. Filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes.",
                "consolidado": "int. Default: 1.",
                "periods":     "int. Default: 8 (quarterly) or 5 (annual).",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="financials", mode="complete", params=\'{"company":"PETR4","grupo":"DRE"}\')',
                'skill(domain="cvm", sub_domain="financials", mode="complete", params=\'{"company":"PETR4","period":"annual","grupo":"BPA"}\')',
            ],
        },
        "summary": {
            "description": "Combined: latest annual + latest quarterly (4Q trend) + key ratios.",
            "include_in_all": True,
            "params": {
                "company":     "str. Required.",
                "consolidado": "int. Default: 1.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="financials", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch financials mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.financials.financials import (
        quarterly, annual, complete, summary,
    )

    dispatch = {
        "quarterly": quarterly,
        "annual": annual,
        "complete": complete,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "financials",
                "mode": mode, "error": str(e)}
