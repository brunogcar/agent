"""Mode: annual -- annual summary + ratios.

Queries DFP annual values (meses=12) + DVA for proventos.
Computes: margins, EBITDA, ROA/ROE, debt ratios, payout.

Registered as "annual" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.fetchers import _build_summary


@register_mode(
    "annual",
    description=(
        "Annual summary + ratios from DFP (default 5 years). "
        "Includes EBITDA, margins, ROA/ROE, debt ratios, payout."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of years. Default: 5.",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="annual", params=\'{"company":"PETR4"}\')',
    ],
)
def annual(company: str = "", periods: int = 5, consolidado: int = 1) -> dict:
    """Annual summary + ratios (default 5 years).

    Queries DFP annual values (meses=12) + DVA for proventos.
    Computes: margins, EBITDA, ROA/ROE, debt ratios, payout.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    return _build_summary(company, periods, consolidado, is_quarterly=False)
