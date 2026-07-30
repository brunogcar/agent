"""skills/cvm/historical/helpers.py — Internal helpers for historical modes.

Three helpers used by both the auto-generated <metric>_history modes (in
_registry.py) and the explicit modes (in modes/):

  - _months_ago(months)              -> date string N months ago (YYYY-MM-DD)
  - _metric_history(company, metric, months) -> wrapped history series
  - _make_metric_history_fn(metric)  -> factory: thin wrapper fn for a metric

These are NOT public modes — they're internal plumbing. The <metric>_history
public modes are auto-registered by _registry._auto_register_metric_history_modes()
using _make_metric_history_fn().
"""
from __future__ import annotations

from datetime import datetime, timedelta

from skills.cvm._freshness import add_freshness
from skills.cvm.calculations._registry import resolve_metric


def _months_ago(months: int) -> str:
    """Return date string N months ago in YYYY-MM-DD format.

    Uses 30 days per month — a coarse approximation suitable for windowing
    daily time-series (the exact boundary doesn't matter much when the
    underlying series is daily).
    """
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
    spec = resolve_metric(metric_name)
    if spec.per_share_label:
        _fn.__doc__ = (
            f"Daily {spec.per_share_label} + {spec.ratio_label} time series "
            f"for the last N months.\n\n"
            f"Args:\n"
            f"    company: Ticker. Required.\n"
            f"    months: Number of months of history. Default: 60 (5 years).\n"
        )
    else:
        _fn.__doc__ = (
            f"Daily {spec.ratio_label} time series "
            f"for the last N months.\n\n"
            f"Args:\n"
            f"    company: Ticker. Required.\n"
            f"    months: Number of months of history. Default: 60 (5 years).\n"
        )
    return _fn
