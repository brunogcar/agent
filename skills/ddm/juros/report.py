"""skills/ddm/juros/report.py - Section builders for the juros dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": "Selic (mes)", "value": "13,65%", "delta": optional}

  Chart section:
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type, data: {labels, datasets}, options}}

  Table section:
    {"type": "table", "title": ..., "description": ...,
     "columns": [...], "rows": [[...], ...], "column_align": [...]}

  Text section:
    {"type": "text", "title": ..., "body": ...}

Chart sections emit a Chart.js config dict in `chart_data` (so the
dashboard.html template can render it via `new Chart(canvas, config)`).
Table `rows` are a list of lists (so the template's data_table macro can
iterate cells directly). Tables that include numeric columns carry a
`column_align` hint that macros.html applies (right-align + tabular-nums).

Juros-specific differences vs inflation/report.py:
  - build_chart_section has THREE datasets (month_value + media_no_ano +
    media_12m), not two. month_value is solid; media_no_ano + media_12m
    are dashed (different colors).
  - build_matrix_table_section has NO "Ano" column (juros pages don't
    ship one). All 12 month columns use diverging red->white->green
    heatmap coloring.
  - build_table_section columns are: Mes/Ano | Indice do mes (%) |
    Media no ano (%) | Media 12 meses (%).
"""

from __future__ import annotations

from skills.ddm.juros.helpers import (
    format_pct, _format_mes_ano, _heat_color, build_observation_rows,
)


# Per-index chart colors (3 indices).
INDEX_COLORS = {
    "selic":      "#0d9488",  # teal
    "meta-selic": "#3b82f6",  # blue
    "cdi":        "#f59e0b",  # amber
}

# Secondary colors for the dashed "media_no_ano" line per index.
INDEX_COLORS_MEDIA_ANO = {
    "selic":      "#5eead4",  # teal-300
    "meta-selic": "#93c5fd",  # blue-300
    "cdi":        "#fcd34d",  # amber-300
}


def build_kpi_card(label: str, value, subtitle: str = "") -> dict:
    """Build a KPI card dict for the top-level kpis list.

    The dashboard template renders k.label + k.value (the other fields
    are kept for debugging / future use but are ignored by the template).

    Args:
        label:    KPI label (e.g. "Selic (mes)").
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

    Each juros index dashboard shows the daily rate (% a.a.) alongside the
    year-to-date average and the rolling 12-month average - mirroring the
    Google Sheet layout used by the analyst.

    Datasets:
      1. month_value   (solid line,  INDEX_COLORS[slug])
      2. media_no_ano  (dashed line, INDEX_COLORS_MEDIA_ANO[slug])
      3. media_12m     (dashed line, slate gray)

    Args:
        title:        Chart title (also used as the section title).
        observations: List of {"ref_date", "month_value", "media_no_ano",
                              "media_12m"} dicts.
        slug:         DDM juros slug (drives color selection).
        description:  Optional description shown above the chart.
    """
    rows = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    labels = [r["ref_date"] for r in rows]
    month_data = [r.get("month_value") for r in rows]
    media_ano_data = [r.get("media_no_ano") for r in rows]
    media_12m_data = [r.get("media_12m") for r in rows]
    color = INDEX_COLORS.get(slug, "#0d9488")
    color_media = INDEX_COLORS_MEDIA_ANO.get(slug, "#5eead4")

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
                        "label":           "Indice do mes (%)",
                        "data":            month_data,
                        "borderColor":     color,
                        "backgroundColor": color,
                        "fill":            False,
                        "tension":         0.3,
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Media no ano (%)",
                        "data":            media_ano_data,
                        "borderColor":     color_media,
                        "backgroundColor": color_media,
                        "fill":            False,
                        "tension":         0.3,
                        "borderDash":      [5, 5],
                        "yAxisID":         "y",
                    },
                    {
                        "label":           "Media 12 meses (%)",
                        "data":            media_12m_data,
                        "borderColor":     "#94a3b8",  # slate-400
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
                    "y": {"title": {"display": True, "text": "% (a.a.)"}},
                },
            },
        },
        # Range selector (same as bcb/macro + b3/price + ddm/inflation charts).
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": month_data,    "label": "Indice do mes (%)"},
            {"data": media_ano_data, "label": "Media no ano (%)"},
            {"data": media_12m_data, "label": "Media 12 meses (%)"},
        ],
        "price_full_data": month_data,
    }


def build_overlay_chart_section(title: str,
                                series: list[dict],
                                description: str = "") -> dict:
    """Build a multi-line overlay chart (for the Comparativo tab).

    Each entry in `series` becomes one dataset:
      {"slug": "selic", "name": "Selic", "observations": [...]}
    The overlay plots month_value for every index over the last N months.

    Args:
        title:       Chart title.
        series:      List of {slug, name, observations} dicts.
        description: Optional description shown above the chart.
    """
    # Union of all ref_dates (sorted ascending). Each dataset uses None for
    # dates missing from its own series.
    all_dates: list[str] = []
    seen: set[str] = set()
    for s in series:
        for obs in s.get("observations", []):
            d = obs.get("ref_date")
            if d and d not in seen:
                seen.add(d)
                all_dates.append(d)
    all_dates.sort()

    datasets = []
    for s in series:
        slug = s.get("slug", "")
        name = s.get("name", slug)
        observations = s.get("observations", [])
        by_date = {o.get("ref_date"): o.get("media_12m") for o in observations}
        data = [by_date.get(d) for d in all_dates]
        datasets.append({
            "label":           f"{name} - media 12m",
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
            "data": {"labels": all_dates, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 24}},
                    "y": {"title": {"display": True, "text": "% (a.a.)"}},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels":    all_dates,
        "price_full_datasets":  [
            {"data": ds["data"], "label": ds["label"]} for ds in datasets
        ],
    }


def build_table_section(title: str, observations: list[dict],
                        limit: int = 0,
                        description: str = "",
                        descending: bool = False) -> dict:
    """Build a historical observations table.

    Columns: Mes/Ano | Indice do mes (%) | Media no ano (%) | Media 12 meses (%)
    Rows are a LIST OF LISTS (NOT list of dicts) so the dashboard template's
    data_table macro can iterate cells directly.
    Numeric columns are right-aligned via column_align.

    If descending=True, rows are reversed (newest first) for display.
    """
    rows = build_observation_rows(observations, limit=limit)
    if descending:
        rows = list(reversed(rows))

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      ["Mes/Ano", "Indice do mes (%)",
                         "Media no ano (%)", "Media 12 meses (%)"],
        "rows":         rows,
        "column_align": ["left", "right", "right", "right"],
        "negative_red": True,
    }


def build_matrix_table_section(title: str, matrix_result: dict,
                               description: str = "") -> dict:
    """Build a year x month matrix heatmap table.

    [v4] Returns type="heatmap" with {text, bg, color} cells.
    All 12 month columns use diverging red->white->green.
    NO "Ano" column (juros are daily rates, not acumulado).
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
