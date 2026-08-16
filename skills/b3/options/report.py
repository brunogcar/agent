"""skills/b3/options/report.py - Section builders for the options dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": ..., "value": <formatted string>, "raw": <float>,
     "unit": ..., "subtitle": ...}

  Chart section:
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type, data: {labels, datasets}, options},
     "price_range_selector": True,
     "price_full_labels": [...], "price_full_datasets": [...]}

  Table section:
    {"type": "table", "title": ..., "description": ...,
     "columns": [...], "rows": [[...], ...]}

  Text section:
    {"type": "text", "title": ..., "body": ...}

  Error section (graceful degradation):
    {"type": "text", "title": ..., "body": "Erro ao consultar: ..."}

Same pattern as skills/bcb/macro/report.py. The default chart line color
is green (#22c55e) since the options skill's primary accent is the call
color (calls = green, puts = red).
"""

from __future__ import annotations


# Default accent colors for the options skill (calls = green, puts = red).
_COLOR_CALL = "#22c55e"
_COLOR_PUT  = "#ef4444"


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
        "value":    value,
        "raw":      value,
        "unit":     unit,
        "subtitle": subtitle,
    }


def build_chart_section(title: str, observations: list[dict],
                        unit: str = "",
                        description: str = "") -> dict:
    """Build a line-chart section from a list of observations.

    Emits a Chart.js config in `chart_data` so the dashboard.html template
    can render it via `new Chart(canvas, config)`.

    Args:
        title:        Chart title (also used as the section title + dataset label).
        observations: List of {"ref_date", "value"} dicts.
        unit:         Unit hint ("% a.d.", "R$", "ratio", etc.) — informational.
        description:  Optional description shown above the chart.

    The default line color is green (#22c55e). Callers that need a
    different palette (e.g. the P/C ratio chart with a dashed grey
    reference line at 1.0) can post-process the returned dict's
    chart_data.data.datasets list directly.
    """
    rows = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    labels = [r["ref_date"] for r in rows]
    data = [r.get("value") for r in rows]

    return {
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
                    "borderColor": _COLOR_CALL,
                    "backgroundColor": _COLOR_CALL,
                    "fill": False,
                    "tension": 0.3,
                    "pointRadius": 1.5,
                    "pointHoverRadius": 4,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                },
            },
        },
        # Time range selector (Tudo/10A/5A/1A/6M/3M/1M). The
        # filterPriceChart JS in dashboard.html reads price_full_datasets
        # to slice data when a button is clicked.
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": data, "label": title},
        ],
        "price_full_data": data,
    }


def build_table_section(title: str, rows: list[list],
                        columns: list[str] | None = None,
                        description: str = "") -> dict:
    """Build a table section with already-built rows (list-of-lists).

    Rows are a LIST OF LISTS (NOT list of dicts) so the dashboard template's
    data_table macro can iterate cells directly: [[c1, c2, ...], ...].

    Args:
        title:       Table title.
        rows:        List of row lists (each row = list of cell values).
        columns:     Column header labels.
        description: Optional description shown above the table.
    """
    return {
        "type":        "table",
        "title":       title,
        "description": description,
        "columns":     columns or [],
        "rows":        rows,
    }


def build_text_section(title: str, body: str) -> dict:
    """Build a plain text section (renders as a styled info box)."""
    return {"type": "text", "title": title, "body": body}


def build_error_section(title: str, error: str) -> dict:
    """Build an error section (used when a sub-query fails gracefully).

    The dashboard stays status=ok with error sections so the rest of the
    tabs still render — mirrors the CVM financials + bcb/macro graceful
    degradation contract.
    """
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
