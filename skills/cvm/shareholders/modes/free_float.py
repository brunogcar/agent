"""Mode: free_float -- free float % + shareholder counts (FRE).

Delegates to data_sources.cvm.fre.query_engine.free_float with bridge
auto-sync.

Registered as "free_float" in skills.cvm.shareholders._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.shareholders._registry import register_mode


@register_mode(
    "free_float",
    description="Free float % + shareholder counts (PF/PJ/institutional).",
    include_in_all=False,
    params={
        "company": "str. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="shareholders", mode="free_float", params=\'{"company":"VALE3"}\')',
    ],
)
def free_float(company: str = "") -> dict:
    """Query free float % + shareholder counts from FRE.

    Delegates to data_sources.cvm.fre.query_engine.free_float.
    Returns: circulation % (ON/PN/total), shareholder counts (PF/PJ/inst).

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.fre.query_engine import free_float as fre_free_float
    return fre_free_float(company=company)
