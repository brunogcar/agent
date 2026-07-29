"""Mode: summary -- ratios + data source availability.

Wraps `ratios()` and adds a `data_availability` block that summarizes which
DBs are synced (price / dfp_ttm / fre_shares). Useful for debugging missing
data without re-running every ratio.

[v1.5] The headline_v13_metrics block has been removed -- all metrics are
now in ratios() directly via compute_all_ratios(), so a separate headline
block was redundant.

Registered as "summary" in skills.cvm.valuation._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.valuation._registry import register_mode
from skills.cvm.valuation.modes.ratios import ratios


@register_mode(
    "summary",
    description="Ratios + data source availability (which DBs are synced).",
    params={
        "company": "str. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="valuation", mode="summary", params=\'{"company":"PETR4"}\')',
    ],
)
def summary(company: str = "") -> dict:
    """Combined: ratios + data source status (which DBs are synced).

    [v1.5] The headline_v13_metrics block has been removed -- all metrics are
    now in ratios() directly via compute_all_ratios(), so a separate headline
    block was redundant.
    """
    r = ratios(company=company)
    if r.get("status") != "ok":
        return r

    r["data_availability"] = {
        "price": r["sources"].get("price", {}).get("status", "missing"),
        "price_source": r["sources"].get("price", {}).get("source", "unknown"),
        "dfp_ttm": r["sources"].get("financials", {}).get("status", "missing"),
        "fre_shares": r["sources"].get("shares", {}).get("status", "missing"),
    }
    return r
