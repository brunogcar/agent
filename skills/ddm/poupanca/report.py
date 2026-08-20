"""skills/ddm/poupanca/report.py - Section builders for the poupanca dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": "Poupanca (mes)", "value": "0,67%", "delta": optional}

  Chart section:
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type, data: {labels, datasets}, options}}

  Table section:
    {"type": "table", "title": ..., "description": ...,
     "columns": [...], "rows": [[...], ...], "column_align": [...],
     "negative_red": True}

  Text section:
    {"type": "text", "title": ..., "body": ...}

Chart sections emit a Chart.js config dict in `chart_data` (so the
dashboard.html template can render it via `new Chart(canvas, config)`).
Table `rows` are a list of lists (so the template's data_table macro can
iterate cells directly). Tables that include numeric columns carry a
`column_align` hint that macros.html applies (right-align + tabular-nums).

Poupanca-specific differences vs juros/report.py:
  - build_chart_section has THREE datasets (month_value + acumulado_no_ano +
    acumulado_12m - SUM-derived, not AVERAGE). month_value is solid;
    acumulado_no_ano + acumulado_12m are dashed (different colors).
  - build_table_section has negative_red=True (poupanca yields can be
    negative during high-inflation periods) + columns: Mes/Ano |
    Rendimento (%) | Acumulado no ano (%) | Acumulado 12m (%).
  - build_matrix_table_section returns type="heatmap" with {text, bg, color}
    cell dicts. NO "Ano" column (poupanca pages don't ship one). All 12
    month columns use diverging red->white->green heatmap coloring.
  - NO build_overlay_chart_section (no Comparativo tab - only 1 index).
"""

from __future__ import annotations

from skills.ddm.poupanca.helpers import (
    format_pct, _format_mes_ano, _heat_color, build_observation_rows,
)


# Poupanca chart color (emerald green - savings theme).
# Only 1 index in this subdomain, so a single color is enough.
POUPANCA_COLOR = "#10b981"

# Secondary color for the dashed "acumulado_no_ano" line.
POUPANCA_COLOR_ACUM_ANO = "#6ee7b7"  # emerald-300

# Color for the dashed "acumulado_12m" line.
POUPANCA_COLOR_ACUM_12M = "#94a3b8"  # slate-400


def build_kpi_card(label: str, value, subtitle: str = "") -> dict:
    """Build a KPI card dict for the top-level kpis list.

    The dashboard template renders k.label + k.value (the other fields
    are kept for debugging / future use but are ignored by the template).

    Args:
        label:    KPI label (e.g. "Poupanca (mes)").
        value:    Float value (will be formatted as PT-BR percentage).
        subtitle: Optional sub-text (e.g. ref_date).
    """
    return {
        "label":    label,
        "value":    format_pct(value),
        "raw":      value,
        "subtitle": subtitle,
    }


def build_chart_section(title: str, observations: list[dict],
                        slug: str = "",
                        description: str = "") -> dict:
    """Build a line-chart section with THREE datasets.

    Each poupanca dashboard shows the monthly yield (%) alongside the
    year-to-date SUM (cumulative return) and the rolling 12-month SUM
    (cumulative return) - mirroring the Google Sheet layout used by the
    analyst.

    Datasets:
      1. month_value        (solid line,  POUPANCA_COLOR - emerald green)
      2. acumulado_no_ano   (dashed line, POUPANCA_COLOR_ACUM_ANO - emerald-300)
      3. acumulado_12m      (dashed line, POUPANCA_COLOR_ACUM_12M - slate-400)

    Args:
        title:        Chart title (also used as the section title).
        observations: List of {"ref_date", "month_value", "acumulado_no_ano",
                              "acumulado_12m"} dicts.
        slug:         DDM poupanca slug (kept for parity with juros; poupanca
                      has only 1 index so the color is constant).
        description:  Optional description shown above the chart.
    """
    _ = slug  # parity with juros signature; poupanca has 1 index

    rows = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    labels = [_format_mes_ano(r["ref_date"]) for r in rows]
    month_data = [r.get("month_value") for r in rows]
    acum_ano_data = [r.get("acumulado_no_ano") for r in rows]
    acum_12m_data = [r.get("acumulado_12m") for r in rows]
    color = POUPANCA_COLOR
    color_acum_ano = POUPANCA_COLOR_ACUM_ANO
    color_acum_12m = POUPANCA_COLOR_ACUM_12M

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
                        "label":           "Rendimento (%)",
                        "data":            month_data,
                        "borderColor":     color,
                        "backgroundColor": color,
                        "fill":            False,
                        "tension":         0.3,
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Acumulado no ano (%)",
                        "data":            acum_ano_data,
                        "borderColor":     color_acum_ano,
                        "backgroundColor": color_acum_ano,
                        "fill":            False,
                        "tension":         0.3,
                        "borderDash":      [5, 5],
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Acumulado 12 meses (%)",
                        "data":            acum_12m_data,
                        "borderColor":     color_acum_12m,
                        "backgroundColor": color_acum_12m,
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
                    "y": {"title": {"display": True, "text": "% (rendimento)"}},
                },
            },
        },
        # Range selector (same as bcb/macro + b3/price + ddm/juros charts).
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": month_data,    "label": "Rendimento (%)"},
            {"data": acum_ano_data, "label": "Acumulado no ano (%)"},
            {"data": acum_12m_data, "label": "Acumulado 12 meses (%)"},
        ],
        "price_full_data": month_data,
    }


def build_table_section(title: str, observations: list[dict],
                        limit: int = 0,
                        description: str = "",
                        descending: bool = False) -> dict:
    """Build a historical observations table.

    Columns: Mes/Ano | Rendimento (%) | Acumulado no ano (%) | Acumulado 12m (%)
    Rows are a LIST OF LISTS (NOT list of dicts) so the dashboard template's
    data_table macro can iterate cells directly.
    Numeric columns are right-aligned via column_align.

    negative_red=True: poupanca yields can be negative during high-inflation
    periods (e.g. when monthly yield < monthly inflation). The dashboard
    template's data_table macro renders negative values in red.

    If descending=True, rows are reversed (newest first) for display.
    """
    # [v3] Sort DESC (newest first) directly — don't rely on build_observation_rows
    sorted_obs = sorted(observations, key=lambda o: o.get("ref_date", ""), reverse=True)
    if limit > 0:
        sorted_obs = sorted_obs[:limit]
    rows = []
    for o in sorted_obs:
        rows.append([
            _format_mes_ano(o.get("ref_date", "")),
            format_pct(o.get("month_value")),
            format_pct(o.get("media_no_ano" if "poupanca" == "juros" else "acumulado_no_ano")),
            format_pct(o.get("media_12m" if "poupanca" == "juros" else "acumulado_12m")),
        ])

    return {
        "type":          "table",
        "title":         title,
        "description":   description,
        "columns":       ["Mes/Ano", "Rendimento (%)",
                          "Acumulado no ano (%)", "Acumulado 12m (%)"],
        "rows":          rows,
        "column_align":  ["left", "right", "right", "right"],
        "negative_red":  True,
    }


def build_matrix_table_section(title: str, matrix_result: dict,
                               description: str = "") -> dict:
    """Build a year x month matrix heatmap table.

    Returns type="heatmap" with {text, bg, color} cell dicts.
    All 12 month columns use diverging red->white->green.
    NO "Ano" column (poupanca is monthly yield, not cumulative).

    IMPORTANT: Returns type="heatmap" (NOT type="table"). This was the bug
    fix in juros v4 that poupanca inherits from day one. The heatmap_table
    macro expects this type and reads the {text, bg, color} dicts from
    each cell directly.
    """
    raw_months = matrix_result.get("months") or []
    years = matrix_result.get("years", [])
    matrix = matrix_result.get("matrix", {})

    canonical = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                 "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    data_labels = [m for m in raw_months if m in canonical]
    if not data_labels:
        data_labels = list(canonical)

    all_vals = []
    for year in years:
        row = matrix.get(year, {})
        for label in data_labels:
            v = row.get(label)
            if v is not None:
                all_vals.append(v)
    vmin = min(all_vals) if all_vals else 0.0
    vmax = max(all_vals) if all_vals else 0.0

    columns = ["Ano"] + data_labels
    align = ["left"] + ["right"] * len(data_labels)

    rows = []
    for year in years:
        row_data = matrix.get(year, {})
        row = [str(year)]
        for label in data_labels:
            v = row_data.get(label)
            row.append(_heat_color(v, vmin, vmax))
        rows.append(row)

    return {
        "type":         "heatmap",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": align,
    }


def build_text_section(title: str, body: str) -> dict:
    """Build a plain text section."""
    return {"type": "text", "title": title, "body": body}


def build_error_section(title: str, error: str) -> dict:
    """Build an error section (used when a sub-query fails gracefully)."""
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
