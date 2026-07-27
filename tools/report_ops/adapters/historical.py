"""adapters/historical.py — Flatten historical skill JSON → chart/table data.

Auto-generated metric chart adapters + metric-aware summary adapter.

Adapters:
  historical_lpa_chart   — dual-dataset chart: LPA (per-share) + P/L (ratio)
  historical_vpa_chart   — dual-dataset chart: VPA (per-share) + P/VPA (ratio)
  historical_summary     — KPI strip + summary table (metric-aware)
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


# ── Metric chart adapter factory ─────────────────────────────────────────────
# Each metric chart shows BOTH the per-share value and the ratio as separate
# datasets. The per-share value and ratio often have different scales (e.g.,
# VPA ~25 vs P/VPA ~1.5), so we emit them as two datasets. The chart builder
# can render them on dual axes if configured.

def _make_metric_chart_adapter(adapter_name: str, metric_name: str,
                                per_share_key: str | None, per_share_label: str | None,
                                ratio_key: str, ratio_label: str):
    """Factory: create a chart adapter for a specific metric.

    For per-share + price ratio metrics (lpa, vpa, dpa, rps):
      Produces a dual-dataset chart with dual-axis support:
        - Per-share value (LPA, VPA, DPA, RPS) on the LEFT axis ("y")
        - Price ratio (P/L, P/VPA, Div Yield, PSR) on the RIGHT axis ("y1")

    For fundamental ratio metrics (roe, roa, roic):
      Produces a single-dataset chart (just the ratio over time, single axis).
      per_share_key is None — no per-share value to show.

    The chart builder (charts.py v1.2.9) detects yAxisID and adds the
    scales config automatically for dual-axis charts.
    """
    def _adapter(result: dict) -> dict:
        if not _ok(result):
            return _error_table(result, title=f"Historical {ratio_label}")

        series = result.get("series") or []
        if not series:
            return _error_table(result, title=f"Historical {ratio_label}")

        x_labels = [s["date"] for s in series]
        ratio_data = [s.get(ratio_key) for s in series]  # None for gaps

        if per_share_key:
            # Per-share + ratio: dual-dataset, dual-axis
            per_share_data = [s.get(per_share_key) for s in series]
            return {
                "x": x_labels,
                "datasets": [
                    {"label": per_share_label, "data": per_share_data, "yAxisID": "y"},
                    {"label": ratio_label, "data": ratio_data, "yAxisID": "y1"},
                ],
            }
        else:
            # Fundamental ratio: single dataset, single axis
            return {
                "x": x_labels,
                "datasets": [
                    {"label": ratio_label, "data": ratio_data},
                ],
            }
    _adapter.__name__ = adapter_name
    _adapter.__qualname__ = adapter_name
    if per_share_label:
        _adapter.__doc__ = (
            f"Flatten historical.{metric_name}_history result into a dual-axis "
            f"chart: {per_share_label} (left axis) + {ratio_label} (right axis)."
        )
    else:
        _adapter.__doc__ = (
            f"Flatten historical.{metric_name}_history result into a "
            f"single-axis chart: {ratio_label} over time."
        )
    return _adapter


# ── Auto-register chart adapters for all registered metrics ──────────────────
# This auto-generates historical_lpa_chart, historical_vpa_chart, etc.
# When a new metric is registered, its chart adapter appears here automatically.

from skills.cvm.calculations._registry import METRICS  # noqa: E402

for _name in sorted(METRICS.keys()):
    _spec = METRICS[_name]
    _adapter_fn = _make_metric_chart_adapter(
        adapter_name=f"historical_{_name}_chart",
        metric_name=_name,
        per_share_key=_spec.per_share_key,
        per_share_label=_spec.per_share_label,
        ratio_key=_spec.ratio_key,
        ratio_label=_spec.ratio_label,
    )
    # Register the adapter in the ADAPTERS dict
    from tools.report_ops.adapters import ADAPTERS  # noqa: E402
    ADAPTERS[f"historical_{_name}_chart"] = _adapter_fn


# ── Summary adapter (metric-aware, reads result["metric"]) ───────────────────

@register_adapter("historical_summary")
def summary(result: dict) -> dict:
    """Flatten historical.summary result into KPI strip + summary table.

    Metric-aware: reads result["metric"] and result["per_share_label"] /
    result["ratio_label"] to render the appropriate labels.

    For per-share + price ratio metrics (lpa, vpa, dpa, rps):
      Displays BOTH the per-share value and the ratio, plus engine-specific components.

    For fundamental ratio metrics (roe, roa, roic):
      Displays only the ratio (no per-share value). per_share_label is None.
    """
    if not _ok(result):
        return _error_table(result, title="Historical Summary")

    metric_name = result.get("metric", "lpa")
    current = result.get("current", {})
    averages = result.get("averages", {})
    rng = result.get("range", {})

    # Get labels from the result (set by the registry-driven summary())
    per_share_label = result.get("per_share_label")
    ratio_label = result.get("ratio_label", "P/L")

    # Find the per-share key and ratio key from the registry
    from skills.cvm.calculations._registry import resolve_metric
    try:
        spec = resolve_metric(metric_name)
        per_share_key = spec.per_share_key
        ratio_key = spec.ratio_key
    except ValueError:
        per_share_key = None
        ratio_key = "pe"

    # KPI strip — shows per-share value (if applicable) + ratio + averages + percentile
    kpis = []
    if per_share_label and per_share_key:
        kpis.append({"label": f"Current {per_share_label}", "value": current.get(per_share_key), "format": "num"})
    kpis.extend([
        {"label": f"Current {ratio_label}",     "value": current.get(ratio_key),     "format": "num"},
        {"label": f"1Y Average {ratio_label}",  "value": averages.get("1y"),         "format": "num"},
        {"label": f"3Y Average {ratio_label}",  "value": averages.get("3y"),         "format": "num"},
        {"label": f"5Y Average {ratio_label}",  "value": averages.get("5y"),         "format": "num"},
        {"label": "Percentile",                 "value": result.get("percentile"),   "format": "num"},
    ])

    # Summary table — metric-aware rows
    rows = [
        [f"Current {ratio_label}",      apply_fmt(current.get(ratio_key), "num")],
    ]
    if per_share_label and per_share_key:
        rows.append([f"Current {per_share_label}",  apply_fmt(current.get(per_share_key), "num")])
    if "price" in current:
        rows.append(["Current Price",               apply_fmt(current.get("price"), "brl_full")])

    # Engine-specific components
    if "ttm_earnings" in current:
        rows.append(["TTM Earnings", apply_fmt(current.get("ttm_earnings"), "brl")])
    if "ttm_rev" in current:
        rows.append(["TTM Revenue", apply_fmt(current.get("ttm_rev"), "brl")])
    if "pl" in current:
        rows.append(["Patrimônio Líquido", apply_fmt(current.get("pl"), "brl")])
    if "shares" in current:
        rows.append(["Shares", apply_fmt(current.get("shares"), "int")])

    rows.extend([
        [f"1Y Average {ratio_label}",   apply_fmt(averages.get("1y"), "num")],
        [f"3Y Average {ratio_label}",   apply_fmt(averages.get("3y"), "num")],
        [f"5Y Average {ratio_label}",   apply_fmt(averages.get("5y"), "num")],
        [f"Min {ratio_label} (5Y)",     apply_fmt(rng.get("min"), "num")],
        [f"Max {ratio_label} (5Y)",     apply_fmt(rng.get("max"), "num")],
        ["Percentile",                  str(result.get("percentile", "")) + "%"],
        ["Interpretation",              result.get("interpretation", "")],
    ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Historical {ratio_label} Summary — {result.get('company','')}",
            "columns": ["Metric", "Value"],
            "rows": rows,
            "formats": {"Metric": "text", "Value": "text"},
            "note": f"Date: {current.get('date','')} | Data points: {result.get('data_points',0)}",
        }],
        "kpis": kpis,
        "sources": [],
    }
