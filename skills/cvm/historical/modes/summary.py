"""Mode: summary -- current ratio vs 1Y/3Y/5Y average + min/max/percentile.

Metric-aware: works for any registered metric (lpa, vpa, dpa, roe, roic,
ev_ebitda, etc.). The current block includes both the per-share value and
the ratio (when applicable), plus engine-specific components.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from skills.cvm._freshness import add_freshness
from skills.cvm.calculations._registry import resolve_metric, list_metrics
from skills.cvm.historical._registry import register_mode
from skills.cvm.historical.helpers import _months_ago


_ALL_METRIC_NAMES = ", ".join(list_metrics())


@register_mode(
    "summary",
    description=(
        "Current ratio vs 1Y/3Y/5Y average + min/max/percentile. "
        "Metric-aware: includes both per-share value and ratio in the result."
    ),
    include_in_all=True,
    params={
        "company": "str. Ticker. Required.",
        "metric": f"str. Metric name or alias ({_ALL_METRIC_NAMES}). Default: lpa.",
        "months": "int. History window for percentile. Default: 60.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="historical", mode="summary", '
        'params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="historical", mode="summary", '
        'params=\'{"company":"PETR4","metric":"vpa"}\')',
    ],
)
def summary(company: str = "", metric: str = "lpa", months: int = 60) -> dict:
    """Current ratio vs 1Y/3Y/5Y average + min/max/percentile.

    Metric-aware: works for any registered metric. The current block includes
    both the per-share value and the ratio, plus engine-specific components.

    Args:
        company: Ticker. Required.
        metric: Metric name or alias. Default: lpa.
        months: History window for percentile (always uses max(months, 60)).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    try:
        spec = resolve_metric(metric)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    # Get 5Y of history for percentiles (even if months < 60)
    date_from = _months_ago(max(months, 60))
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = spec.history_fn(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}'"}

    # Extract ratio values (filter None and <= 0) — percentile based on RATIO
    ratio_key = spec.ratio_key
    ratio_values = [s[ratio_key] for s in series
                    if s.get(ratio_key) is not None and s[ratio_key] > 0]

    if not ratio_values:
        return {"status": "not_found",
                "error": f"No valid {spec.ratio_label} data for '{company}' "
                         f"(possibly negative earnings/equity)"}

    current_ratio = ratio_values[-1]
    current_date = series[-1]["date"]

    # Compute averages for different windows (based on ratio)
    def _avg(window_days: int) -> float | None:
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        vals = [s[ratio_key] for s in series
                if s.get(ratio_key) is not None and s[ratio_key] > 0
                and s["date"] >= cutoff]
        return sum(vals) / len(vals) if vals else None

    avg_1y = _avg(365)
    avg_3y = _avg(365 * 3)
    avg_5y = _avg(365 * 5)

    # Percentile: what % of historical ratio values are below the current ratio
    sorted_values = sorted(ratio_values)
    percentile = None
    for i, v in enumerate(sorted_values):
        if v >= current_ratio:
            percentile = round(i / len(sorted_values) * 100, 1)
            break

    min_value = min(ratio_values)
    max_value = max(ratio_values)

    # Interpretation (based on ratio percentile)
    if percentile is not None:
        if percentile <= 25:
            interpretation = "cheap (below 25th percentile of history)"
        elif percentile >= 75:
            interpretation = "expensive (above 75th percentile of history)"
        else:
            interpretation = "fair (between 25th-75th percentile of history)"
    else:
        interpretation = "unknown"

    # Build current block — includes ratio + per-share value (if applicable) + components
    current_block = {
        "date": current_date,
        spec.ratio_key: round(current_ratio, 2),
    }
    # Add per-share value if this metric has one (None for fundamental ratios)
    if spec.per_share_key:
        current_block[spec.per_share_key] = (
            round(series[-1].get(spec.per_share_key), 4)
            if series[-1].get(spec.per_share_key) is not None else None
        )
    # Add price if the series has it (fundamental metrics may not)
    if "price" in series[-1]:
        current_block["price"] = series[-1]["price"]
    # Include engine-specific fields from the series entry
    for key in ("ttm_earnings", "ttm_rev", "pl", "shares", "lpa", "dpa"):
        if key in series[-1]:
            current_block[key] = series[-1][key]

    result = {
        "status": "ok",
        "company": company,
        "metric": spec.name,
        "per_share_label": spec.per_share_label,
        "ratio_label": spec.ratio_label,
        "current": current_block,
        "averages": {
            "1y": round(avg_1y, 2) if avg_1y else None,
            "3y": round(avg_3y, 2) if avg_3y else None,
            "5y": round(avg_5y, 2) if avg_5y else None,
        },
        "range": {
            "min": round(min_value, 2),
            "max": round(max_value, 2),
        },
        "percentile": percentile,
        "interpretation": interpretation,
        "data_points": len(ratio_values),
        "date_range": {"from": date_from, "to": date_to},
    }

    return add_freshness(result)
