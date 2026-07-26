"""skills/cvm/historical/historical.py -- Historical ratios main logic.

Orchestrates engines + metrics to produce time series and summaries.

MODES
-----
  pe_history (default) -- daily P/L time series
  ratio_history        -- any metric over time (pe only for now)
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


# ── Mode: ratio_history ──────────────────────────────────────────────────────

def ratio_history(company: str = "", metric: str = "pe", months: int = 60) -> dict:
    """Any metric over time. Currently only pe is implemented.

    Args:
        company: Ticker. Required.
        metric: Metric name (pe, pvpa, ev_ebitda). Default: pe.
        months: Number of months. Default: 60.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    metric = metric.strip().lower()

    if metric == "pe":
        return pe_history(company=company, months=months)
    elif metric == "pvpa":
        return {"status": "not_implemented", "error": "pvpa metric not yet implemented (stub)"}
    elif metric == "ev_ebitda":
        return {"status": "not_implemented", "error": "ev_ebitda metric not yet implemented (stub)"}
    else:
        return {"status": "error", "error": f"Unknown metric '{metric}'. Available: pe"}


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "", metric: str = "pe", months: int = 60) -> dict:
    """Current ratio vs 1Y/3Y/5Y average + min/max/percentile.

    Tells you if a stock is cheap vs its own history.

    Args:
        company: Ticker. Required.
        metric: Metric name. Default: pe.
        months: History window for percentile. Default: 60.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    metric = metric.strip().lower()
    if metric != "pe":
        return {"status": "not_implemented", "error": f"summary for '{metric}' not yet implemented"}

    from skills.cvm.historical.metrics.pe import pe_history as _pe_history

    # Get 5Y of history for percentiles (even if months < 60)
    date_from = _months_ago(max(months, 60))
    date_to = datetime.now().strftime("%Y-%m-%d")

    series = _pe_history(company, date_from, date_to)

    if not series:
        return {"status": "not_found",
                "error": f"No price data for '{company}'"}

    # Extract P/L values (filter None)
    pe_values = [s["pe"] for s in series if s.get("pe") is not None and s["pe"] > 0]

    if not pe_values:
        return {"status": "not_found",
                "error": f"No valid P/L data for '{company}' (possibly negative earnings)"}

    current_pe = pe_values[-1]
    current_date = series[-1]["date"]

    # Compute averages for different windows
    def _avg(window_days: int) -> float | None:
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        vals = [s["pe"] for s in series if s.get("pe") is not None and s["pe"] > 0
                and s["date"] >= cutoff]
        return sum(vals) / len(vals) if vals else None

    avg_1y = _avg(365)
    avg_3y = _avg(365 * 3)
    avg_5y = _avg(365 * 5)

    # Percentile: what % of historical P/L values are below the current P/L
    sorted_pe = sorted(pe_values)
    percentile = None
    for i, v in enumerate(sorted_pe):
        if v >= current_pe:
            percentile = round(i / len(sorted_pe) * 100, 1)
            break

    # Min/max
    min_pe = min(pe_values)
    max_pe = max(pe_values)

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

    result = {
        "status": "ok",
        "company": company,
        "metric": "pe",
        "current": {
            "date": current_date,
            "pe": round(current_pe, 2),
            "price": series[-1].get("price"),
            "ttm_earnings": series[-1].get("ttm_earnings"),
            "shares": series[-1].get("shares"),
        },
        "averages": {
            "1y": round(avg_1y, 2) if avg_1y else None,
            "3y": round(avg_3y, 2) if avg_3y else None,
            "5y": round(avg_5y, 2) if avg_5y else None,
        },
        "range": {
            "min": round(min_pe, 2),
            "max": round(max_pe, 2),
        },
        "percentile": percentile,
        "interpretation": interpretation,
        "data_points": len(pe_values),
        "date_range": {"from": date_from, "to": date_to},
    }

    return add_freshness(result)
