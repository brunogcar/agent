"""skills/cvm/historical/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape summary() results (one per metric) into a multi-tab dashboard
payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).

Dashboard tab shape (produced by modes/dashboard.py):
  - Overview:             Summary text section (company + per-metric status)
  - Percentile Analysis:  table showing min/25th/median/75th/max/current/
                          percentile/interpretation per metric
  - Trend:                table showing current + 1Y/3Y averages + 1Y/3Y
                          change per metric
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from tools.report_ops.formats import apply_fmt

from skills.cvm.calculations._registry import resolve_metric
from skills.cvm.historical.helpers import _months_ago


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _num(v: Any) -> Any:
    """Coerce numeric strings/values to int or float (passthrough None)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _kpi(label: str, value: Any, spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted via apply_fmt so the adapter can pass it
    through verbatim. When value is None, falls back to "—".
    """
    if value is None:
        return {"label": label, "value": "—", "unit": unit}
    return {"label": label, "value": _fmt(value, spec), "unit": unit}


def _ok(d: dict | None) -> bool:
    """True if d is a dict with status='ok'."""
    return isinstance(d, dict) and d.get("status") == "ok"


# ── Quartile computation ─────────────────────────────────────────────────────
# summary() gives us min/max/percentile but NOT the 25th / median / 75th.
# The dashboard's Percentile Analysis tab wants the full distribution, so
# we re-fetch the series + compute quartiles here. This is a separate call
# from summary() but the underlying engines cache aggressively, so the cost
# is negligible.

def compute_quartiles(series: list[dict], ratio_key: str) -> dict | None:
    """Compute min, p25, median, p75, max for a ratio series.

    Filters to positive ratio values (same filter summary() applies). Returns
    None when no valid values exist.
    """
    if not series:
        return None
    vals = sorted(
        s[ratio_key] for s in series
        if s.get(ratio_key) is not None and s[ratio_key] > 0
    )
    if not vals:
        return None
    n = len(vals)

    def _pct(p: float) -> float:
        # Nearest-rank percentile — matches summary()'s percentile semantics.
        idx = min(int(round(p / 100 * (n - 1))), n - 1)
        return vals[idx]

    return {
        "min":    vals[0],
        "p25":    _pct(25),
        "median": _pct(50),
        "p75":    _pct(75),
        "max":    vals[-1],
        "count":  n,
    }


def fetch_quartiles(company: str, metric_name: str, months: int = 60) -> dict | None:
    """Fetch series for a metric + return quartiles dict, or None on failure.

    Used by the dashboard mode to enrich each per-metric summary with the
    25th/median/75th percentiles (which summary() doesn't expose).
    """
    try:
        spec = resolve_metric(metric_name)
        date_from = _months_ago(max(months, 60))
        date_to = datetime.now().strftime("%Y-%m-%d")
        series = spec.history_fn(company, date_from, date_to)
        return compute_quartiles(series, spec.ratio_key)
    except Exception:
        return None


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(summaries: dict, metric_defs: list[tuple[str, str, str]]) -> list[dict]:
    """Build KPI cards for the dashboard top-level kpis list.

    One KPI per metric in `metric_defs`. Each card shows the current ratio
    value pre-formatted via the appropriate format spec:
      - "ratio" unit -> "num" format (raw multiple like 5.23 for P/L)
      - "pct" unit   -> "pct" format (0.185 -> "18,50%")

    Args:
        summaries:      {metric_name: summary_result} dict (one per metric).
        metric_defs:    list of (metric_name, label, unit) tuples.
                        unit is "ratio" for price multiples (P/L, P/VPA,
                        EV/EBITDA), "pct" for profitability/yield ratios
                        (ROE, ROIC, Div Yield).
    """
    kpis = []
    for metric_name, label, unit in metric_defs:
        s = summaries.get(metric_name) or {}
        if not _ok(s):
            kpis.append(_kpi(label, None, "num", unit))
            continue
        try:
            spec = resolve_metric(metric_name)
        except ValueError:
            kpis.append(_kpi(label, None, "num", unit))
            continue
        current = s.get("current", {})
        value = current.get(spec.ratio_key)
        # Map unit -> format spec for pre-formatting.
        spec_str = "pct" if unit == "pct" else "num"
        kpis.append(_kpi(label, value, spec_str, unit))
    return kpis


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(summaries: dict, metric_defs: list[tuple[str, str, str]],
                            company: str) -> dict:
    """Build the Overview tab's text section summarizing the dashboard data.

    Multi-line text showing company + per-metric status (current value or
    dash when the underlying summary() failed).
    """
    lines = [f"Company: {company}", "Metrics covered:"]
    for metric_name, label, unit in metric_defs:
        s = summaries.get(metric_name) or {}
        if not _ok(s):
            lines.append(f"  - {label}: unavailable")
            continue
        try:
            spec = resolve_metric(metric_name)
        except ValueError:
            lines.append(f"  - {label}: unavailable")
            continue
        current = s.get("current", {})
        value = current.get(spec.ratio_key)
        spec_str = "pct" if unit == "pct" else "num"
        lines.append(f"  - {label}: {_fmt(value, spec_str)}")
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(lines),
    }


def _scaled(value: Any, scale: float) -> Any:
    """Multiply a value by scale (e.g. 100 to convert 0.18 -> 18), rounding to 4dp.

    Returns None when value is None. Used to convert pct-kind metrics
    (stored as 0-1 fractions) to percentages for display in tables.
    """
    if value is None:
        return None
    return round(value * scale, 4)


def _change(curr: Any, avg: Any) -> Any:
    """Compute (curr - avg) / avg as a fraction, rounded to 4dp.

    Returns None when either input is None or avg is zero.
    """
    if curr is None or avg is None or avg == 0:
        return None
    return round((curr - avg) / avg, 4)


# ── Percentile Analysis tab section (table) ──────────────────────────────────

def build_percentile_section(summaries: dict, quartiles: dict,
                              metric_defs: list[tuple[str, str, str]]) -> dict:
    """Build the Percentile Analysis tab table.

    Columns: Metric, Current, Min, 25th, Median, 75th, Max, Percentile,
    Interpretation.

    Args:
        summaries:  {metric_name: summary_result} dict.
        quartiles:  {metric_name: quartiles_dict | None} dict (from
                    fetch_quartiles).
        metric_defs: list of (metric_name, label, unit) tuples.
    """
    columns = ["Metric", "Current", "Min", "25th", "Median",
               "75th", "Max", "Percentile", "Interpretation"]
    formats = {c: "num" for c in columns[1:-1]}
    formats["Metric"] = "text"
    formats["Interpretation"] = "text"
    rows = []
    for metric_name, label, unit in metric_defs:
        s = summaries.get(metric_name) or {}
        q = quartiles.get(metric_name) or {}
        if not _ok(s):
            rows.append([label] + ["—" for _ in columns[1:]])
            continue
        try:
            spec = resolve_metric(metric_name)
        except ValueError:
            rows.append([label] + ["—" for _ in columns[1:]])
            continue
        current = s.get("current", {}).get(spec.ratio_key)
        # For pct-kind metrics, multiply ratio values by 100 so the column
        # renders as 18.50 instead of 0.185 (matches the KPI display).
        scale = 100.0 if unit == "pct" else 1.0
        rows.append([
            label,
            _num(_scaled(current, scale)),
            _num(_scaled(q.get("min"),    scale)),
            _num(_scaled(q.get("p25"),    scale)),
            _num(_scaled(q.get("median"), scale)),
            _num(_scaled(q.get("p75"),    scale)),
            _num(_scaled(q.get("max"),    scale)),
            s.get("percentile"),
            s.get("interpretation", "—"),
        ])
    return {
        "title": "Percentile Analysis (5Y)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (
            "Where current values sit vs their 5Y historical distribution. "
            "Percentile = % of historical data points BELOW the current value. "
            "Pct-kind metrics (ROE, ROIC, Div Yield) shown as percentages; "
            "ratio-kind metrics (P/L, P/VPA, EV/EBITDA) shown as raw multiples."
        ),
    }


# ── Trend tab section (table) ────────────────────────────────────────────────

def build_trend_section(summaries: dict,
                         metric_defs: list[tuple[str, str, str]]) -> dict:
    """Build the Trend tab table.

    Columns: Metric, Current, 1Y Avg, 1Y Change, 3Y Avg, 3Y Change.
    Change = (current - avg) / avg as a fraction (0.10 = +10%).
    """
    columns = ["Metric", "Current", "1Y Avg", "1Y Change",
               "3Y Avg", "3Y Change"]
    formats = {
        "Metric":    "text",
        "Current":   "num",
        "1Y Avg":    "num",
        "1Y Change": "pct",
        "3Y Avg":    "num",
        "3Y Change": "pct",
    }
    rows = []
    for metric_name, label, unit in metric_defs:
        s = summaries.get(metric_name) or {}
        if not _ok(s):
            rows.append([label] + ["—" for _ in columns[1:]])
            continue
        try:
            spec = resolve_metric(metric_name)
        except ValueError:
            rows.append([label] + ["—" for _ in columns[1:]])
            continue
        current = s.get("current", {}).get(spec.ratio_key)
        avgs = s.get("averages", {})
        avg_1y = avgs.get("1y")
        avg_3y = avgs.get("3y")
        scale = 100.0 if unit == "pct" else 1.0
        rows.append([
            label,
            _num(_scaled(current, scale)),
            _num(_scaled(avg_1y,   scale)),
            _num(_change(current, avg_1y)),
            _num(_scaled(avg_3y,   scale)),
            _num(_change(current, avg_3y)),
        ])
    return {
        "title": "Trend (Current vs 1Y/3Y averages)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (
            "Latest value vs 1-year and 3-year averages. Change = "
            "(current - avg) / avg as a fraction (0.10 = +10%). Pct-kind "
            "metrics scaled to percentages; ratio-kind shown as raw multiples."
        ),
    }
