"""skills/bcb/macro/report.py - Section builders for the macro dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": "Selic", "value": "13.15%", "delta": optional}

  Chart section:
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type, data: {labels, datasets}, options}}

  Table section:
    {"type": "table", "title": ..., "description": ...,
     "columns": ["Data", "Valor"], "rows": [[date_str, value_str], ...]}

  Text section:
    {"type": "text", "title": ..., "body": ...}

[v3] Chart sections now emit a Chart.js config dict in `chart_data`
(was: separate `labels` + `values` arrays at top level - the template
ignored those). Table `rows` are now a list of lists (was: list of dicts)
so the template's data_table macro can iterate cells directly.
[v1.6] Added sortable/default_sort/sort_types/negative_red/column_align +
collapsible params to build_table_section.
[v1.7] Added collapsible param to build_chart_section + build_table_section.
"""

from __future__ import annotations

from skills.bcb.macro.helpers import format_value, build_observation_rows


# Per-unit chart colors. Picked to match the CVM financials palette.
_UNIT_COLOR = {
    "% a.d.": "#0d9488",
    "% a.a.": "#0d9488",
    "%":      "#f59e0b",
    "R$":     "#3b82f6",
    "R$ mil": "#3b82f6",
}


def build_kpi_card(label: str, value, unit: str = "",
                   subtitle: str = "") -> dict:
    """Build a KPI card dict for the top-level kpis list.

    The dashboard template renders k.label + k.value (the other fields
    are kept for debugging / future use but are ignored by the template).

    Returns:
        {"label": ..., "value": <formatted string>, "raw": <float>,
         "unit": ..., "subtitle": ...}
    """
    return {
        "label":    label,
        "value":    format_value(value, unit),
        "raw":      value,
        "unit":     unit,
        "subtitle": subtitle,
    }


def build_chart_section(title: str, observations: list[dict],
                        unit: str = "",
                        description: str = "",
                        collapsible: bool = False) -> dict:
    """Build a line-chart section from a list of observations.

    Emits a Chart.js config in `chart_data` so the dashboard.html template
    can render it via `new Chart(canvas, config)`.

    Args:
        title:        Chart title (also used as the section title).
        observations: List of {"ref_date", "value"} dicts.
        unit:         BCB unit ("% a.d.", "%", "R$", etc.) - drives color.
        description:  Optional description shown above the chart.
        collapsible:  If True, the chart section renders inside a collapsible
                      container (collapsed by default). Default False.
    """
    rows = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    labels = [r["ref_date"] for r in rows]
    data = [r.get("value") for r in rows]
    color = _UNIT_COLOR.get(unit, "#0d9488")

    section = {
        "type":        "chart",
        "title":       title,
        "unit":        unit,
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title,
                    "data": data,
                    "borderColor": color,
                    "backgroundColor": color,
                    "fill": False,
                    "tension": 0.3,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                },
            },
        },
        # [v3] Time range selector - same as price chart (Tudo/10A/5A/1A/6M/3M/1M)
        # [v1.3-v2] Added price_full_datasets (required by the template's
        # filterPriceChart JS — without it the range buttons render but
        # clicking them does nothing).
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": data, "label": title},
        ],
        "price_full_data": data,
    }
    if collapsible:
        section["collapsible"] = True
    return section


def build_table_section(title: str, observations: list[dict],
                        unit: str = "",
                        limit: int = 0,
                        description: str = "",
                        sortable: bool = True,
                        default_sort: dict | None = None,
                        sort_types: list[str] | None = None,
                        negative_red: bool = False,
                        column_align: list[str] | None = None,
                        collapsible: bool = False) -> dict:
    """Build a table section from a list of observations.

    Rows are a LIST OF LISTS so the dashboard template's data_table macro
    can iterate cells directly: [[date_cell, value_str], ...].

    [v2] Now accepts sortable/default_sort/sort_types/negative_red/column_align
    params (passed through to the data_table Jinja macro). Default:
    sortable=True with Data DESC (newest first). Date cells are dicts with
    {text: DD/MM/YYYY, data-value: YYYY-MM-DD} for chronological sorting.
    [v1.7] Added collapsible param — renders the table inside a collapsible
    container (collapsed by default) so charts are visible without scrolling.

    Args:
        title:        Section title.
        observations: List of {"ref_date", "value"} dicts.
        unit:         BCB unit for value formatting.
        limit:        Max rows (0 = all). Takes the last `limit` after ASC sort.
        description:  Optional description.
        sortable:     Whether the table has clickable sort headers. Default True.
        default_sort: {"column": int, "direction": "asc"|"desc"}. Default
                      column 0 DESC (newest date first).
        sort_types:   Per-column sort type ("text" or "number"). Default
                      ["text", "number"].
        negative_red: Whether negative values render in red. Default False.
        column_align: Per-column alignment ("left" or "right"). Default
                      ["left", "right"].
        collapsible:  If True, renders inside a collapsible container. Default False.
    """
    if default_sort is None:
        default_sort = {"column": 0, "direction": "desc"}
    if sort_types is None:
        sort_types = ["text", "number"]
    if column_align is None:
        column_align = ["left", "right"]

    section = {
        "type":         "table",
        "title":        title,
        "unit":         unit,
        "description":  description,
        "columns":      ["Data", "Valor"],
        "rows":         build_observation_rows(observations, unit=unit, limit=limit),
        "sortable":     sortable,
        "default_sort": default_sort,
        "sort_types":   sort_types,
        "negative_red": negative_red,
        "column_align": column_align,
    }
    if collapsible:
        section["collapsible"] = True
    return section


def build_text_section(title: str, body: str) -> dict:
    """Build a plain text section."""
    return {"type": "text", "title": title, "body": body}


def build_error_section(title: str, error: str) -> dict:
    """Build an error section (used when a sub-query fails gracefully)."""
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
