"""skills/ddm/inflation/report.py - Section builders for the inflation dashboard.

[v2] Changes:
  - build_matrix_table_section: now emits heatmap cells with {text, bg, color}
    dicts instead of plain strings. Jan-Dez use diverging red→white→green
    (negative=red, zero=white, positive=green). "Ano" column uses sequential
    white→blue. No hardcoded values — min/max computed dynamically from data.
  - Chart labels use _format_mes_ano for display ("Jul/2026" not "2026-07").
"""
from __future__ import annotations

from skills.ddm.inflation.helpers import (
    format_pct, build_observation_rows, _format_mes_ano, _heat_color,
)


INDEX_COLORS = {
    "igp-m": "#3b82f6",
    "ipca":  "#f59e0b",
    "inpc":  "#a855f7",
}


def build_kpi_card(label: str, value, subtitle: str = "") -> dict:
    return {
        "label":    label,
        "value":    format_pct(value),
        "raw":      value,
        "subtitle": subtitle,
    }


def build_chart_section(title: str, observations: list[dict],
                        slug: str = "", description: str = "") -> dict:
    rows = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    # [v2] Use _format_mes_ano for display labels
    labels = [_format_mes_ano(r["ref_date"]) for r in rows]
    month_data = [r.get("month_value") for r in rows]
    year_acum_data = [r.get("year_acumulado") for r in rows]
    acum12m_data = [r.get("acumulado_12m") for r in rows]
    color = INDEX_COLORS.get(slug, "#3b82f6")

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label":           "Variacao no mes (%)",
                        "data":            month_data,
                        "borderColor":     color,
                        "backgroundColor": color,
                        "fill":            False,
                        "tension":         0.3,
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Acumulado no ano (%)",
                        "data":            year_acum_data,
                        "borderColor":     "#a855f7",
                        "backgroundColor": "#a855f7",
                        "fill":            False,
                        "tension":         0.3,
                        "borderDash":      [5, 5],
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Acumulado 12 meses (%)",
                        "data":            acum12m_data,
                        "borderColor":     "#94a3b8",
                        "backgroundColor": "#94a3b8",
                        "fill":            False,
                        "tension":         0.3,
                        "borderDash":      [2, 4],
                        "yAxisID":         "y",
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": "% (a.m.)"}},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": month_data,     "label": "Variacao no mes (%)"},
            {"data": year_acum_data, "label": "Acumulado no ano (%)"},
            {"data": acum12m_data,   "label": "Acumulado 12 meses (%)"},
        ],
        "price_full_data": month_data,
    }


def build_overlay_chart_section(title: str, series: list[dict],
                                description: str = "") -> dict:
    all_dates: list[str] = []
    seen: set[str] = set()
    for s in series:
        for obs in s.get("observations", []):
            d = obs.get("ref_date")
            if d and d not in seen:
                seen.add(d)
                all_dates.append(d)
    all_dates.sort()

    # [v2] Use _format_mes_ano for display labels
    display_labels = [_format_mes_ano(d) for d in all_dates]

    datasets = []
    for s in series:
        slug = s.get("slug", "")
        name = s.get("name", slug)
        observations = s.get("observations", [])
        by_date = {o.get("ref_date"): o.get("acumulado_12m") for o in observations}
        data = [by_date.get(d) for d in all_dates]
        datasets.append({
            "label":           f"{name} - acum. 12m",
            "data":            data,
            "borderColor":     INDEX_COLORS.get(slug, "#64748b"),
            "backgroundColor": INDEX_COLORS.get(slug, "#64748b"),
            "fill":            False,
            "tension":         0.3,
        })

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": display_labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 24}},
                    "y": {"title": {"display": True, "text": "% (acum. 12m)"}},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels":    display_labels,
        "price_full_datasets":  [
            {"data": ds["data"], "label": ds["label"]} for ds in datasets
        ],
    }


def build_table_section(title: str, observations: list[dict],
                        limit: int = 0, description: str = "") -> dict:
    """Build a historical observations table.

    [v2] DESC sort (newest first). Date display uses _format_mes_ano.
    """
    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      ["Mes/Ano", "Indice do mes (%)",
                         "Acumulado no ano (%)", "Acumulado 12m (%)"],
        "rows":         build_observation_rows(observations, limit=limit),
        "column_align": ["left", "right", "right", "right"],
        "negative_red": True,
    }


def build_matrix_table_section(title: str, matrix_result: dict,
                               description: str = "") -> dict:
    """Build a year x month matrix table with heatmap colors.

    [v2] Now emits heatmap cells with {text, bg, color} dicts.
    - Jan-Dez columns: diverging red→white→green (negative=red, zero=white, positive=green)
    - "Ano" column: sequential white→blue (higher=darker blue)
    - min/max computed dynamically from the actual data (no hardcoded values)
    """
    raw_months = matrix_result.get("months") or []
    years = matrix_result.get("years", [])
    matrix = matrix_result.get("matrix", {})

    data_labels = list(raw_months)
    while data_labels and data_labels[0] in ("", "Ano", "Mes", "Ano / Mes"):
        data_labels = data_labels[1:]
    if not data_labels:
        data_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                       "Jul", "Ago", "Set", "Out", "Nov", "Dez", "Ano"]

    columns = ["Ano"] + data_labels
    align = ["left"] + ["right"] * len(data_labels)

    # [v2] Compute min/max for each color scheme
    # Monthly values (Jan-Dez): all values across all years + months
    monthly_values = []
    annual_values = []
    for year in years:
        row_data = matrix.get(year, {})
        for label in data_labels:
            val = row_data.get(label)
            if val is not None:
                if label == "Ano":
                    annual_values.append(val)
                else:
                    monthly_values.append(val)

    monthly_min = min(monthly_values) if monthly_values else 0.0
    monthly_max = max(monthly_values) if monthly_values else 0.0
    annual_min = min(annual_values) if annual_values else 0.0
    annual_max = max(annual_values) if annual_values else 0.0

    # Build rows with heatmap cells
    rows = []
    for year in years:
        row_data = matrix.get(year, {})
        row = [str(year)]
        for label in data_labels:
            val = row_data.get(label)
            if label == "Ano":
                cell = _heat_color(val, annual_min, annual_max, "sequential")
            else:
                cell = _heat_color(val, monthly_min, monthly_max, "diverging")
            row.append(cell)
        rows.append(row)

    # Heatmap uses "type": "heatmap" so macros.html renders it with bg/color
    return {
        "type":         "heatmap",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": align,
    }


def build_text_section(title: str, body: str) -> dict:
    return {"type": "text", "title": title, "body": body}


def build_error_section(title: str, error: str) -> dict:
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
