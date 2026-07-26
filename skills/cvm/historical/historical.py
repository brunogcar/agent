"""skills/cvm/historical/historical.py -- Historical ratios main logic.

Orchestrates engines + metrics (via the metric registry) to produce time
series and summaries. All metric dispatch is registry-driven — adding a new
metric = drop a file in metrics/ + register_metric(). No edits here.

MODES (auto-generated from the registry):
  lpa_history    -- daily LPA + P/L time series (from lpa metric)
  vpa_history    -- daily VPA + P/VPA time series (from vpa metric)
  ratio_history  -- any metric over time (generic, takes metric param)
  summary        -- current vs 1Y/3Y/5Y average + percentile (generic)

NO SYNC
-------
Read-only. Assumes COTAHIST + DFP + ITR + FRE are already synced.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from skills.cvm._freshness import add_freshness
from skills.cvm.historical.metrics._registry import resolve_metric, list_metrics, METRICS


def _months_ago(months: int) -> str:
    """Return date string N months ago in YYYY-MM-DD format."""
    d = datetime.now() - timedelta(days=months * 30)
    return d.strftime("%Y-%m-%d")


# ── Generic metric history (used by auto-generated <metric>_history modes) ───

def _metric_history(company: str, metric_name: str, months: int) -> dict:
    """Run a metric's history function and wrap the result.

    This is the shared implementation behind every <metric>_history mode.
    Each <metric>_history mode is a thin wrapper that calls this with the
    canonical metric name.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    spec = resolve_metric(metric_name)

    date_from = _months_ago(months)
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = spec.history_fn(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}' in period {date_from} to {date_to}"}

    # Count how many have a valid ratio
    ratio_count = sum(1 for s in series if s.get(spec.ratio_key) is not None)

    result = {
        "status": "ok",
        "company": company,
        "metric": spec.name,
        "per_share_label": spec.per_share_label,
        "ratio_label": spec.ratio_label,
        "date_from": date_from,
        "date_to": date_to,
        "total_days": len(series),
        f"{spec.ratio_key}_days": ratio_count,
        "series": series,
    }

    return add_freshness(result)


# ── Auto-generated <metric>_history modes ────────────────────────────────────
# These are thin wrappers around _metric_history(). The MANIFEST in __init__.py
# auto-generates entries for each registered metric. When you add a new metric,
# a new <metric>_history function appears here automatically — but since Python
# requires the function to exist at module level, we generate them dynamically.

def _make_metric_history_fn(metric_name: str):
    """Factory: create a <metric>_history function for a registered metric."""
    def _fn(company: str = "", months: int = 60) -> dict:
        return _metric_history(company, metric_name, months)
    _fn.__name__ = f"{metric_name}_history"
    _fn.__qualname__ = f"{metric_name}_history"
    _fn.__doc__ = (
        f"Daily {resolve_metric(metric_name).per_share_label} + "
        f"{resolve_metric(metric_name).ratio_label} time series "
        f"for the last N months.\n\n"
        f"Args:\n"
        f"    company: Ticker. Required.\n"
        f"    months: Number of months of history. Default: 60 (5 years).\n"
    )
    return _fn


# Generate lpa_history, vpa_history, etc. for every registered metric
for _metric_name in list_metrics():
    _fn = _make_metric_history_fn(_metric_name)
    globals()[f"{_metric_name}_history"] = _fn


# ── Mode: ratio_history (generic) ────────────────────────────────────────────

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


# ── Mode: summary (generic, metric-aware) ────────────────────────────────────

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

    # Build current block — includes BOTH per-share value and ratio + components
    current_block = {
        "date": current_date,
        spec.per_share_key: (
            round(series[-1].get(spec.per_share_key), 4)
            if series[-1].get(spec.per_share_key) is not None else None
        ),
        spec.ratio_key: round(current_ratio, 2),
        "price": series[-1].get("price"),
    }
    # Include engine-specific fields from the series entry
    for key in ("ttm_earnings", "pl", "shares"):
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
