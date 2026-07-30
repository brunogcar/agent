"""Mode: shareholders -- named shareholders with ownership % (FRE).

Delegates to data_sources.cvm.fre.query_engine.shareholders with bridge
auto-sync.

Registered as "shareholders" in skills.cvm.shareholders._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.shareholders._registry import register_mode


@register_mode(
    "shareholders",
    description="Named shareholders with ownership % (ON/PN/total) + controlling status.",
    include_in_all=False,
    params={
        "company": "str. B3 ticker (PETR4), name fragment, or CNPJ. Required.",
        "limit":   "int. Max shareholders. Default: 50.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params=\'{"company":"PETR4"}\')',
    ],
)
def shareholders(company: str = "", limit: int = 50) -> dict:
    """Query named shareholders with ownership % from FRE.

    Delegates to data_sources.cvm.fre.query_engine.shareholders.
    Returns: list of shareholders (name, CNPJ/CPF, ON/PN/total %, controlling).

    Args:
        company: B3 ticker (PETR4), name fragment, or CNPJ. Required.
        limit:   Max shareholders to return. Default: 50.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.fre.query_engine import shareholders as fre_shareholders
    return fre_shareholders(company=company, limit=limit)
