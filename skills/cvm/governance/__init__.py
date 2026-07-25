"""skills/cvm/governance/__init__.py -- Governance skill manifest + router.

Combines CGVN data (governance practices) with bridge resolution.
Read-only — no sync. Calls data_sources.cvm.cgvn.query_engine directly.

Example:
  skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "governance",
    "description": (
        "Governance practices analysis from CGVN disclosures. "
        "practices: all practices for latest filing. "
        "score: governance score (% Sim/Não/Parcialmente). "
        "by_chapter: grouped by chapter."
    ),
    "source":  "cgvn.db (CGVN — Código de Governança e Melhores Práticas)",
    "storage": "read-only — no own database",
    "modes": {
        "practices": {
            "description": "All governance practices for latest filing (recommended vs adopted).",
            "include_in_all": False,
            "params": {
                "company": "str. Ticker, name, or CNPJ. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="governance", mode="practices", params=\'{"company":"PETR4"}\')',
            ],
        },
        "score": {
            "description": "Governance score: % of practices adopted (Sim), partial (Parcialmente), not adopted (Não).",
            "include_in_all": True,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="governance", mode="score", params=\'{"company":"PETR4"}\')',
            ],
        },
        "by_chapter": {
            "description": "Practices grouped by chapter (Capitulo) with adoption counts.",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="governance", mode="by_chapter", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch governance mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.governance.governance import practices, score, by_chapter

    dispatch = {
        "practices": practices,
        "score": score,
        "by_chapter": by_chapter,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "governance",
                "mode": mode, "error": str(e)}
