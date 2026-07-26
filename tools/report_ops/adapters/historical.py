"""adapters/historical.py — Flatten historical skill JSON → chart/table data.

Adapters:
  historical_pe_chart    — line chart of P/L over time
  historical_vpa_chart   — line chart of P/VPA over time
  historical_summary     — KPI strip + summary table (metric-aware: pe or vpa)
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


@register_adapter("historical_pe_chart")
def pe_chart(result: dict) -> dict:
    """Flatten historical.pe_history result into a multi-series chart config.

    Produces the multi-series chart data shape:
        {"x": [dates], "datasets": [{"label": "P/L", "data": [values]}]}
    None P/L values are converted to null (Chart.js handles gaps).
    """
    if not _ok(result):
        return _error_table(result, title="Historical P/L")

    series = result.get("series") or []
    if not series:
        return _error_table(result, title="Historical P/L")

    x_labels = [s["date"] for s in series]
    pe_data = [s.get("pe") for s in series]  # None for gaps

    return {
        "x": x_labels,
        "datasets": [{"label": "P/L", "data": pe_data}],
    }


@register_adapter("historical_vpa_chart")
def vpa_chart(result: dict) -> dict:
    """Flatten historical.vpa_history result into a multi-series chart config.

    Produces the multi-series chart data shape:
        {"x": [dates], "datasets": [{"label": "P/VPA", "data": [values]}]}
    None P/VPA values are converted to null (Chart.js handles gaps).
    """
    if not _ok(result):
        return _error_table(result, title="Historical P/VPA")

    series = result.get("series") or []
    if not series:
        return _error_table(result, title="Historical P/VPA")

    x_labels = [s["date"] for s in series]
    vpa_data = [s.get("vpa") for s in series]  # None for gaps

    return {
        "x": x_labels,
        "datasets": [{"label": "P/VPA", "data": vpa_data}],
    }


@register_adapter("historical_summary")
def summary(result: dict) -> dict:
    """Flatten historical.summary result into KPI strip + summary table.

    Metric-aware: reads result["metric"] ("pe" or "vpa") and renders the
    appropriate labels and engine-specific rows.
    """
    if not _ok(result):
        return _error_table(result, title="Historical Summary")

    metric = (result.get("metric") or "pe").lower()
    current = result.get("current", {})
    averages = result.get("averages", {})
    rng = result.get("range", {})

    # Metric-specific labels + value keys
    if metric == "vpa":
        label = "P/VPA"
        value_key = "vpa"
    else:
        label = "P/L"
        value_key = "pe"

    # KPI strip
    kpis = [
        {"label": f"Current {label}", "value": current.get(value_key), "format": "num"},
        {"label": "1Y Average",  "value": averages.get("1y"), "format": "num"},
        {"label": "3Y Average",  "value": averages.get("3y"), "format": "num"},
        {"label": "5Y Average",  "value": averages.get("5y"), "format": "num"},
        {"label": "Percentile",  "value": result.get("percentile"), "format": "num"},
    ]

    # Summary table — metric-aware rows
    rows = [
        [f"Current {label}",       apply_fmt(current.get(value_key), "num")],
        ["Current Price",          apply_fmt(current.get("price"), "brl_full")],
    ]
    if metric == "vpa":
        rows.append(["Patrimônio Líquido", apply_fmt(current.get("pl"), "brl")])
    else:
        rows.append(["TTM Earnings",       apply_fmt(current.get("ttm_earnings"), "brl")])
    rows.extend([
        ["Shares",                 apply_fmt(current.get("shares"), "int")],
        [f"1Y Average {label}",    apply_fmt(averages.get("1y"), "num")],
        [f"3Y Average {label}",    apply_fmt(averages.get("3y"), "num")],
        [f"5Y Average {label}",    apply_fmt(averages.get("5y"), "num")],
        [f"Min {label} (5Y)",      apply_fmt(rng.get("min"), "num")],
        [f"Max {label} (5Y)",      apply_fmt(rng.get("max"), "num")],
        ["Percentile",             str(result.get("percentile", "")) + "%"],
        ["Interpretation",         result.get("interpretation", "")],
    ])

    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": f"Historical {label} Summary — {result.get('company','')}",
            "columns": ["Metric", "Value"],
            "rows": rows,
            "formats": {"Metric": "text", "Value": "text"},
            "note": f"Date: {current.get('date','')} | Data points: {result.get('data_points',0)}",
        }],
        "kpis": kpis,
        "sources": [],
    }
