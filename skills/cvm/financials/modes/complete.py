"""Mode: complete -- full statements by grupo + key account codes.

Fetches the key account codes (not all 497) for either quarterly or annual
periods. Used when the caller wants the raw statement lines (not the
summary metrics) — e.g. to inspect a specific account.

Registered as "complete" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.metrics import KEY_CODES_BY_GRUPO
from skills.cvm.financials.fetchers import (
    _fetch_complete_annual,
    _fetch_complete_quarterly,
)


@register_mode(
    "complete",
    description=(
        "Full statements by grupo + key account codes (not all 497). "
        "Default period=quarterly."
    ),
    params={
        "company":     "str. Required.",
        "period":      "str. 'quarterly' (default) or 'annual'.",
        "grupo":       "str. Filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes.",
        "consolidado": "int. Default: 1.",
        "periods":     "int. Default: 8 (quarterly) or 5 (annual).",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="complete", params=\'{"company":"PETR4","grupo":"DRE"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="complete", params=\'{"company":"PETR4","period":"annual","grupo":"BPA"}\')',
    ],
)
def complete(
    company: str = "",
    period: str = "quarterly",
    grupo: str = "",
    consolidado: int = 1,
    periods: int = 8,
) -> dict:
    """Full statements by grupo + key account codes (not all 497).

    Args:
        company: Ticker, name, or CNPJ.
        period: "quarterly" (default) or "annual".
        grupo: Statement group filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes.
        consolidado: 1=consolidated, 0=individual.
        periods: Number of periods. Default: 8 (quarterly) or 5 (annual).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    period = period.strip().lower()
    if period not in ("quarterly", "annual"):
        return {"status": "error", "error": f"period must be 'quarterly' or 'annual', got '{period}'"}

    # Determine which codes to fetch
    if grupo:
        grupo = grupo.strip().upper()
        if grupo not in KEY_CODES_BY_GRUPO:
            return {"status": "error",
                    "error": f"Unknown grupo '{grupo}'. Available: {list(KEY_CODES_BY_GRUPO.keys())}"}
        codes_to_fetch = KEY_CODES_BY_GRUPO[grupo]
    else:
        # All key codes from all grupos
        codes_to_fetch = []
        for codes in KEY_CODES_BY_GRUPO.values():
            codes_to_fetch.extend(codes)
        codes_to_fetch = list(set(codes_to_fetch))

    if period == "quarterly":
        return _fetch_complete_quarterly(company, codes_to_fetch, grupo, consolidado, periods)
    else:
        return _fetch_complete_annual(company, codes_to_fetch, grupo, consolidado, periods)
