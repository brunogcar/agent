"""Mode: quarterly -- standalone quarterly summary + ratios.

Derives standalone quarters from ITR cumulative + DFP annual.
Computes: margins, EBITDA, ROA/ROE (annualized), debt ratios, payout.

Registered as "quarterly" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.fetchers import _build_summary


@register_mode(
    "quarterly",
    description=(
        "Standalone quarterly summary + ratios (default 8 quarters). "
        "Derives Q1-Q4 from ITR cumulative + DFP annual."
    ),
    params={
        "company":     "str. B3 ticker (PETR4), name, or CNPJ. Required.",
        "periods":     "int. Number of quarters. Default: 8.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="quarterly", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="quarterly", params=\'{"company":"VALE3","periods":12}\')',
    ],
)
def quarterly(company: str = "", periods: int = 8, consolidado: int = 1) -> dict:
    """Standalone quarterly summary + ratios (default 8 quarters).

    Derives standalone quarters from ITR cumulative + DFP annual.
    Computes: margins, EBITDA, ROA/ROE (annualized), debt ratios, payout.

    Args:
        company: Ticker, name, or CNPJ.
        periods: Number of quarters. Default: 8.
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    return _build_summary(company, periods, consolidado, is_quarterly=True)
