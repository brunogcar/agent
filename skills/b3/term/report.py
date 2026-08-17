"""skills/b3/term/report.py - Section builders for the term dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

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

Same pattern as skills/b3/options/report.py. The default chart line color
is blue (#3b82f6) — the term skill's primary accent (term price = blue,
spot price = teal, volume bars = orange).
"""

from __future__ import annotations


# Default accent colors for the term skill.
# term price = blue, spot price = teal, volume bars = orange.
_COLOR_TERM   = "#3b82f6"
_COLOR_SPOT   = "#0d9488"
_COLOR_VOLUME = "#f59e0b"


def build_chart_section(title: str, observations: list[dict],
                        unit: str = "",
                        description: str = "") -> dict:
    """Build a line-chart section from a list of observations.

    Emits a Chart.js config in `chart_data` so the dashboard.html template
    can render it via `new Chart(canvas, config)`.

    Args:
        title:        Chart title (also used as the section title + dataset label).
        observations: List of {"ref_date", "value"} dicts.
        unit:         Unit hint ("R$", "R$ mil", etc.) — informational.
        description:  Optional description shown above the chart.

    The default line color is blue (#3b82f6) — the term skill's primary
    accent. Callers that need a different palette (e.g. the spread chart
    with term + spot + spread lines, or the volume bar chart) can
    post-process the returned dict's chart_data.data.datasets list directly,
    or build the section inline.
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
                    "borderColor": _COLOR_TERM,
                    "backgroundColor": _COLOR_TERM,
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
    return {"type": "text", "title": title, "text": body}


def build_error_section(title: str, error: str) -> dict:
    """Build an error section (used when a sub-query fails gracefully).

    The dashboard stays status=ok with error sections so the rest of the
    tabs still render — mirrors the CVM financials + bcb/macro + b3/options
    graceful degradation contract.
    """
    return {"type": "text", "title": title,
            "text": f"Erro ao consultar: {error}"}
