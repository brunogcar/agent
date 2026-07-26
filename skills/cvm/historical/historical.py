"""skills/cvm/historical/historical.py -- Historical ratios main logic.

Orchestrates engines + metrics to produce time series and summaries.

MODES
-----
  pe_history (default) -- daily P/L time series
  vpa_history          -- daily P/VPA time series
  ratio_history        -- any metric over time (pe or vpa)
  summary              -- current vs 1Y/3Y/5Y average + percentile

NO SYNC
-------
Read-only. Assumes COTAHIST + DFP + ITR + FRE are already synced.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from skills.cvm._freshness import add_freshness


def _months_ago(months: int) -> str:
    """Return date string N months ago in YYYY-MM-DD format."""
    d = datetime.now() - timedelta(days=months * 30)
    return d.strftime("%Y-%m-%d")


# ── Metric dispatch helpers ──────────────────────────────────────────────────
# Maps metric name → (history_fn, value_key, label_pt)
# history_fn: function(company, date_from, date_to) -> list[dict]
# value_key:  the key in each series entry holding the ratio value
# label_pt:   human-readable label for the metric (used in error messages)

def _metric_dispatch(metric: str):
    """Return (history_fn, value_key, label_pt) for a metric name.

    Raises ValueError for unknown metrics.
    """
    metric = metric.strip().lower()
    if metric == "pe":
        from skills.cvm.historical.metrics.pe import pe_history as _fn
        return _fn, "pe", "P/L"
    elif metric == "vpa":
        from skills.cvm.historical.metrics.vpa import vpa_history as _fn
        return _fn, "vpa", "P/VPA"
    else:
        raise ValueError(
            f"Unknown metric '{metric}'. Available: pe, vpa"
        )


# ── Mode: pe_history (default) ───────────────────────────────────────────────

def pe_history(company: str = "", months: int = 60) -> dict:
    """Daily P/L time series for the last N months.

    Args:
        company: Ticker. Required.
        months: Number of months of history. Default: 60 (5 years).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from skills.cvm.historical.metrics.pe import pe_history as _pe_history

    date_from = _months_ago(months)
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = _pe_history(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}' in period {date_from} to {date_to}"}

    # Count how many have valid PE
    pe_count = sum(1 for s in series if s.get("pe") is not None)

    result = {
        "status": "ok",
        "company": company,
        "metric": "pe",
        "date_from": date_from,
        "date_to": date_to,
        "total_days": len(series),
        "pe_days": pe_count,
        "series": series,
    }

    return add_freshness(result)


# ── Mode: vpa_history ────────────────────────────────────────────────────────

def vpa_history(company: str = "", months: int = 60) -> dict:
    """Daily P/VPA time series for the last N months.

    Args:
        company: Ticker. Required.
        months: Number of months of history. Default: 60 (5 years).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from skills.cvm.historical.metrics.vpa import vpa_history as _vpa_history

    date_from = _months_ago(months)
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = _vpa_history(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}' in period {date_from} to {date_to}"}

    # Count how many have valid VPA
    vpa_count = sum(1 for s in series if s.get("vpa") is not None)

    result = {
        "status": "ok",
        "company": company,
        "metric": "vpa",
        "date_from": date_from,
        "date_to": date_to,
        "total_days": len(series),
        "vpa_days": vpa_count,
        "series": series,
    }

    return add_freshness(result)


# ── Mode: ratio_history ──────────────────────────────────────────────────────

def ratio_history(company: str = "", metric: str = "pe", months: int = 60) -> dict:
    """Any metric over time. Currently: pe, vpa.

    Args:
        company: Ticker. Required.
        metric: Metric name (pe, vpa). Default: pe.
        months: Number of months. Default: 60.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    metric = metric.strip().lower()

    if metric == "pe":
        return pe_history(company=company, months=months)
    elif metric == "vpa":
        return vpa_history(company=company, months=months)
    else:
        return {"status": "error",
                "error": f"Unknown metric '{metric}'. Available: pe, vpa"}


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "", metric: str = "pe", months: int = 60) -> dict:
    """Current ratio vs 1Y/3Y/5Y average + min/max/percentile.

    Tells you if a stock is cheap vs its own history.

    Args:
        company: Ticker. Required.
        metric: Metric name (pe, vpa). Default: pe.
        months: History window for percentile. Default: 60.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    metric = metric.strip().lower()

    try:
        history_fn, value_key, label = _metric_dispatch(metric)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    # Get 5Y of history for percentiles (even if months < 60)
    date_from = _months_ago(max(months, 60))
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = history_fn(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}'"}

    # Extract ratio values (filter None and <= 0)
    values = [s[value_key] for s in series
              if s.get(value_key) is not None and s[value_key] > 0]

    if not values:
        return {"status": "not_found",
                "error": f"No valid {label} data for '{company}' "
                         f"(possibly negative earnings/equity)"}

    current_value = values[-1]
    current_date = series[-1]["date"]

    # Compute averages for different windows
    def _avg(window_days: int) -> float | None:
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        vals = [s[value_key] for s in series
                if s.get(value_key) is not None and s[value_key] > 0
                and s["date"] >= cutoff]
        return sum(vals) / len(vals) if vals else None

    avg_1y = _avg(365)
    avg_3y = _avg(365 * 3)
    avg_5y = _avg(365 * 5)

    # Percentile: what % of historical values are below the current value
    sorted_values = sorted(values)
    percentile = None
    for i, v in enumerate(sorted_values):
        if v >= current_value:
            percentile = round(i / len(sorted_values) * 100, 1)
            break

    # Min/max
    min_value = min(values)
    max_value = max(values)

    # Interpretation
    if percentile is not None:
        if percentile <= 25:
            interpretation = "cheap (below 25th percentile of history)"
        elif percentile >= 75:
            interpretation = "expensive (above 75th percentile of history)"
        else:
            interpretation = "fair (between 25th-75th percentile of history)"
    else:
        interpretation = "unknown"

    # Build current block — include metric-specific extras
    current_block = {
        "date": current_date,
        metric: round(current_value, 2),
        "price": series[-1].get("price"),
    }
    # Include the engine-specific fields from the series entry
    if metric == "pe":
        current_block["ttm_earnings"] = series[-1].get("ttm_earnings")
        current_block["shares"] = series[-1].get("shares")
    elif metric == "vpa":
        current_block["pl"] = series[-1].get("pl")
        current_block["shares"] = series[-1].get("shares")

    result = {
        "status": "ok",
        "company": company,
        "metric": metric,
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
        "data_points": len(values),
        "date_range": {"from": date_from, "to": date_to},
    }

    return add_freshness(result)
