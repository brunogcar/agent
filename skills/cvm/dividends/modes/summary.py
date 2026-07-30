"""Mode: summary -- combined: recent events + annual trend + last payable.

Aggregates from B3 (history) + DFP (annual, payable). Each section is
best-effort — if a data source is missing, the summary still returns
what's available.

Registered as "summary" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py. This is the
default include_in_all mode for the dividends skill.
"""
from __future__ import annotations

from typing import Any

from skills.cvm.dividends._registry import register_mode
from skills.cvm.dividends.modes.history import history
from skills.cvm.dividends.modes.annual import annual
from skills.cvm.dividends.modes.payable import payable


@register_mode(
    "summary",
    description="Combined: recent events + annual trend + last payable.",
    include_in_all=True,
    params={
        "company": "str. Required (ticker preferred).",
    },
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="summary", params=\'{"company":"PETR4"}\')',
    ],
)
def summary(company: str = "") -> dict:
    """Combined: recent dividend events + annual trend + last payable.

    Aggregates from B3 (history) + DFP (annual, payable). Each section is
    best-effort — if a data source is missing, the summary still returns
    what's available.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # 1. Recent dividend events (B3) — best-effort
    try:
        hist = history(company=company, limit=10)
        if hist.get("status") == "ok":
            result["sections"]["recent_events"] = {
                "ticker": hist.get("ticker", ""),
                "count": hist.get("count", 0),
                "events": hist.get("dividends", [])[:5],
            }
        else:
            result["sections"]["recent_events"] = {"status": hist.get("status"),
                                                   "error": hist.get("error", "")}
    except Exception as e:
        result["sections"]["recent_events"] = {"status": "error", "error": str(e)}

    # 2. Annual declared totals (DFP DVA) — best-effort
    try:
        ann = annual(company=company, periods=3)
        if ann.get("status") == "ok":
            result["sections"]["annual_trend"] = {
                "company": ann.get("company", ""),
                "periods": ann.get("periods", []),
            }
        else:
            result["sections"]["annual_trend"] = {"status": ann.get("status"),
                                                  "error": ann.get("error", "")}
    except Exception as e:
        result["sections"]["annual_trend"] = {"status": "error", "error": str(e)}

    # 3. Latest payable (DFP BPP) — best-effort
    try:
        pay = payable(company=company, periods=1)
        if pay.get("status") == "ok" and pay.get("periods"):
            result["sections"]["payable"] = pay["periods"][0]
        else:
            result["sections"]["payable"] = {"status": pay.get("status"),
                                             "error": pay.get("error", "")}
    except Exception as e:
        result["sections"]["payable"] = {"status": "error", "error": str(e)}

    return result
