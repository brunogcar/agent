"""skills/cvm/shareholders/__init__.py -- Shareholders skill manifest + router.

Combines FRE (named shareholders, free float) + DFP (equity structure in BRL).

Data sources used:
  - data_sources/cvm/fre  (posicao_acionaria, distribuicao_capital)
  - data_sources/cvm/dfp  (BPP 2.03.* Patrimônio Líquido)

No sync — read-only over already-synced data.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "shareholders",
    "description": (
        "Shareholder + equity structure. "
        "Named shareholders (FRE) + free float (FRE) + equity breakdown in BRL (DFP BPP). "
        "Accepts B3 ticker (via bridge), name, or CNPJ."
    ),
    "source":  "fre.db (posicao_acionaria, distribuicao_capital) + dfp.db (BPP 2.03.*)",
    "storage": "read-only — no own database",
    "modes": {
        "shareholders": {
            "description": "Named shareholders with ownership % (ON/PN/total) + controlling status.",
            "include_in_all": False,
            "params": {
                "company": "str. B3 ticker (PETR4), name fragment, or CNPJ. Required.",
                "limit":   "int. Max shareholders. Default: 50.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params=\'{"company":"PETR4"}\')',
            ],
        },
        "free_float": {
            "description": "Free float % + shareholder counts (PF/PJ/institutional).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="shareholders", mode="free_float", params=\'{"company":"VALE3"}\')',
            ],
        },
        "equity_structure": {
            "description": "Equity breakdown in BRL (capital, reservas, minority) over N periods.",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
                "periods": "int. Number of fiscal years. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params=\'{"company":"PETR4"}\')',
                'skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params=\'{"company":"VALE3","periods":3}\')',
            ],
        },
        "summary": {
            "description": "Combined: top shareholders + free float + latest equity total.",
            "include_in_all": True,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="shareholders", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch shareholders mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.shareholders.shareholders import (
        shareholders, free_float, equity_structure, summary,
    )

    dispatch = {
        "shareholders": shareholders,
        "free_float": free_float,
        "equity_structure": equity_structure,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "shareholders",
                "mode": mode, "error": str(e)}
