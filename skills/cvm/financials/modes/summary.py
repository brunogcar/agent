"""Mode: summary -- combined latest annual + latest quarterly + key ratios.

Best-effort composition: if one data source is missing, returns what's
available.

[v1.3] Now also includes a `current_ratios` section with calculations
metrics (ROIC, Graham Number, EV/EBITDA, P/FCF) computed at today's date.
These are point-in-time ratios delegated to skills.cvm.calculations.* —
they complement (not replace) the per-period ratios computed by
`compute_ratios()` on raw statement data. Calculations metrics are wrapped
in _safe_call so a missing DB (e.g. cotahist for price-based ratios)
returns None instead of crashing the whole summary.

[v1.5] The current_ratios block now delegates to
`compute_all_ratios(company, today, categories=[...], exclude=[...])`
instead of hardcoding 6 metric imports. This surfaces ALL registered
calculations metrics in the profitability / liquidity / leverage /
efficiency / growth / tax categories (currently 25 metrics) and
auto-picks up any new metric registered via `register_metric()` — no
manual wiring needed. Per-share metrics (lpa, vpa, dpa, rps) are
excluded because they belong in the valuation skill.

Registered as "summary" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.helpers import _safe_call
from skills.cvm.financials.modes.annual import annual
from skills.cvm.financials.modes.quarterly import quarterly


@register_mode(
    "summary",
    description="Combined: latest annual + latest quarterly (4Q trend) + key ratios.",
    params={
        "company":     "str. Required.",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="summary", params=\'{"company":"PETR4"}\')',
    ],
)
def summary(company: str = "", consolidado: int = 1) -> dict:
    """Combined: latest annual + latest quarterly + key ratios.

    Best-effort — if one data source is missing, returns what's available.

    [v1.3] Now also includes a `current_ratios` section with calculations
    metrics (ROIC, Graham Number, EV/EBITDA, P/FCF) computed at today's date.
    These are point-in-time ratios delegated to skills.cvm.calculations.* —
    they complement (not replace) the per-period ratios computed by
    `compute_ratios()` on raw statement data. Calculations metrics are wrapped
    in _safe_call so a missing DB (e.g. cotahist for price-based ratios)
    returns None instead of crashing the whole summary.

    [v1.5] The current_ratios block now delegates to
    `compute_all_ratios(company, today, categories=[...], exclude=[...])`
    instead of hardcoding 6 metric imports. This surfaces ALL registered
    calculations metrics in the profitability / liquidity / leverage /
    efficiency / growth / tax categories (currently 25 metrics) and
    auto-picks up any new metric registered via `register_metric()` — no
    manual wiring needed. Per-share metrics (lpa, vpa, dpa, rps) are
    excluded because they belong in the valuation skill.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # Latest annual (1 year)
    try:
        ann = annual(company=company, periods=1, consolidado=consolidado)
        if ann.get("status") == "ok" and ann.get("periods"):
            result["sections"]["latest_annual"] = ann["periods"][0]
        else:
            result["sections"]["latest_annual"] = {"status": ann.get("status"),
                                                   "error": ann.get("error", "")}
    except Exception as e:
        result["sections"]["latest_annual"] = {"status": "error", "error": str(e)}

    # Latest quarterly (4 quarters for context)
    try:
        qrt = quarterly(company=company, periods=4, consolidado=consolidado)
        if qrt.get("status") == "ok" and qrt.get("periods"):
            # [v1.0.1 P1 fix] periods are sorted oldest-first, so latest = periods[-1]
            result["sections"]["latest_quarterly"] = qrt["periods"][-1]
            result["sections"]["quarterly_trend"] = qrt["periods"]
        else:
            result["sections"]["latest_quarterly"] = {"status": qrt.get("status"),
                                                       "error": qrt.get("error", "")}
    except Exception as e:
        result["sections"]["latest_quarterly"] = {"status": "error", "error": str(e)}

    # [v1.5] Current ratios from calculations registry — auto-surfaces ALL
    # registered metrics in the requested categories. Lazy import so
    # importing financials does NOT trigger calculations imports (and the
    # corresponding PLANNER_MODEL env-var requirement). compute_all_ratios
    # catches exceptions per-metric so one failing metric returns None
    # instead of poisoning the rest.
    today = date.today().isoformat()
    try:
        from skills.cvm.calculations._registry import compute_all_ratios

        result["sections"]["current_ratios"] = {
            "date": today,
            **compute_all_ratios(
                company,
                today,
                categories=["profitability", "liquidity", "leverage",
                            "efficiency", "growth", "tax"],
                exclude=["lpa", "vpa", "dpa", "rps"],  # per-share metrics belong in valuation
            ),
        }
    except Exception as e:
        # If calculations library itself is unavailable (circular import,
        # registry not initialized, etc.), record the error without crashing.
        result["sections"]["current_ratios"] = {"date": today, "error": str(e)}

    return result
