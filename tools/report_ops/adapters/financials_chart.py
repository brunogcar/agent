"""adapters/financials_chart.py — Flatten financials quarterly JSON → chart data.

Adapters:
  financials_quarterly_chart — multi-series line chart of Receita, EBITDA,
  Lucro Líquido over time (standalone quarters).

The adapter produces the multi-series chart data shape:
    {"x": ["1T26","4T25",...], "datasets": [{"label":"Receita","data":[...]}, ...]}

which charts._to_chartjs_config() renders as one line per metric.
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table


# Metrics to plot — each becomes one line. (label, metrics_key)
# Money metrics only (all BRL) so the y-axis is consistent.
_CHART_METRICS = [
    ("Receita Líquida",  "receita_liquida"),
    ("EBITDA",           "ebitda"),
    ("Lucro Líquido",    "lucro_liquido"),
]


@register_adapter("financials_quarterly_chart")
def quarterly_chart(result: dict) -> dict:
    """Flatten financials.quarterly result into multi-series chart data.

    Produces: {"x": [period labels oldest-first], "datasets": [{label, data}]}
    so charts.build() renders a multi-line trend chart.
    """
    if not _ok(result):
        # Return a minimal error shape that the chart builder can render
        return {"x": [], "y": [], "_error": _error_table(result, title="Financials Chart")}

    periods = result.get("periods") or []
    if not periods:
        return {"x": [], "y": [], "_error": _error_table(result, title="Financials Chart")}

    # Sort oldest-first for a left-to-right timeline
    sorted_p = sorted(periods,
                      key=lambda p: (p.get("year", 0), p.get("quarter", 0)))
    x_labels = [p.get("period", "?") for p in sorted_p]

    datasets = []
    for label, key in _CHART_METRICS:
        data = []
        for p in sorted_p:
            m = p.get("metrics") or {}
            v = m.get(key)
            data.append(v if v is not None else None)
        datasets.append({"label": label, "data": data})

    return {"x": x_labels, "datasets": datasets}
