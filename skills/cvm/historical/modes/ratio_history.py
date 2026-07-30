"""Mode: ratio_history -- any metric over time (generic, alias-aware).

Accepts any registered metric name or alias and dispatches to the shared
_metric_history() implementation. The list of accepted names is generated
at import time from the calculations registry — adding a new metric
automatically widens what ratio_history accepts (no edits here).
"""
from __future__ import annotations

from skills.cvm.historical._registry import register_mode
from skills.cvm.historical.helpers import _metric_history
from skills.cvm.calculations._registry import resolve_metric, list_metrics


_ALL_METRIC_NAMES = ", ".join(list_metrics())


@register_mode(
    "ratio_history",
    description=f"Any metric over time. Accepts: {_ALL_METRIC_NAMES} (+ aliases).",
    include_in_all=False,
    params={
        "company": "str. Ticker. Required.",
        "metric": f"str. Metric name or alias ({_ALL_METRIC_NAMES}). Default: lpa.",
        "months": "int. Number of months. Default: 60.",
    },
    examples=[
        f'skill(domain="cvm", sub_domain="historical", mode="ratio_history", '
        f'params=\'{{"company":"PETR4","metric":"vpa","months":120}}\')',
    ],
)
def ratio_history(company: str = "", metric: str = "lpa", months: int = 60) -> dict:
    """Any metric over time. Accepts canonical names and aliases.

    Args:
        company: Ticker. Required.
        metric: Metric name or alias (lpa, pe, pl, p/l, vpa, pvpa, p/vpa).
                Default: lpa.
        months: Number of months. Default: 60.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    try:
        spec = resolve_metric(metric)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    return _metric_history(company, spec.name, months)
