"""skills/ddm/focus/report.py - Section builders for the focus dashboard.

[v1] Two table builders + one chart builder + KPI + error:

  - build_year_table(title, indicators, year, description):
      Table for ONE year, all indicators as rows.
      Columns: Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.
      Sortable: True. Default sort: Indicador ASC (column 0).
      Comp column: colored glyph (up=green, down=red, flat=gray).
      Values displayed as-is (already PT-BR-formatted from the source).

  - build_indicator_table(title, years_data, indicator, description):
      Table for ONE indicator, all years as rows.
      Columns: Ano | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.
      Sortable: True. Default sort: Ano ASC (column 0).
      Comp column: colored glyph.

  - build_indicator_chart(title, years_data, indicator, description):
      Grouped bar chart showing how expectations for this indicator
      evolved across years. 3 datasets (Ha 4 semanas, 1 sem, Hoje) in
      teal/amber/blue. X-axis: years. Y-axis: numeric value (parsed
      from PT-BR string).

  - build_kpi_card(label, value, subtitle)
  - build_error_section(title, error)

Section titles don't repeat the indicator/year (already in tab name).
"""
from __future__ import annotations

from skills._base.kpi import build_kpi_card
from skills._base.error import build_error_section
from skills.ddm.focus.helpers import (
    format_value, format_int, comparison_symbol, comparison_color,
    parse_numeric,
)


# Chart palette for the 3 time-window datasets:
#   - "Ha 4 semanas" -> teal (4 weeks ago - oldest of the three)
#   - "1 sem"        -> amber (1 week ago - middle)
#   - "Hoje"         -> blue (today - most recent)
_WINDOW_COLORS = {
    "four_weeks_ago": "#14b8a6",  # teal-500
    "one_week_ago":   "#f59e0b",  # amber-500
    "today":          "#3b82f6",  # blue-500
}

_WINDOW_LABELS = {
    "four_weeks_ago": "Ha 4 semanas",
    "one_week_ago":   "1 sem",
    "today":          "Hoje",
}


def _value_cell(value, indicator: str = "") -> str:
    """Render a value cell as plain string.

    [v2] Now passes the indicator name to format_value() so it can determine
    the display unit (%, R$, US$ mi) for float values (C2 schema migration).
    None / empty -> "-".
    """
    return format_value(value, indicator=indicator)


def _comparison_cell(comp) -> dict:
    """Build a comparison cell with text + color.

    The cell renders the Unicode glyph (up/down/=) colored green / red /
    gray. The macros.html data_table macro reads {"text": ..., "color": ...}
    and applies the color override inline.
    """
    return {
        "text":  comparison_symbol(comp),
        "color": comparison_color(comp),
    }


def _respondents_cell(value) -> dict:
    """Build a respondents cell with text + data-value (for sortable tables).

    The data-value attribute lets the JS sortTable() function sort the
    Resp. column numerically (149 before 1500, not lexicographically).
    """
    text = format_int(value)
    data_value = str(value) if value is not None else "0"
    cell = {"text": text}
    if value is not None:
        cell["data-value"] = data_value
    return cell


def _value_numeric_cell(value, indicator: str = "") -> dict:
    """Build a value cell with text + data-value (for sortable tables).

    Numeric values (percentages / currencies) carry a data-value attribute
    holding the parsed float so the JS sorter can sort them accurately
    even when the displayed text has PT-BR formatting.

    [v2] Now passes the indicator name to format_value() for proper unit
    display (C2 schema migration — values are floats, not PT-BR strings).
    """
    cell = {"text": _value_cell(value, indicator=indicator)}
    parsed = parse_numeric(value)
    if parsed is not None:
        cell["data-value"] = f"{parsed:.6f}"
    return cell


def build_year_table(title: str, indicators: list[dict],
                     year: int = 0, description: str = "") -> dict:
    """Build the per-year indicators table.

    One row per indicator (IPCA, PIB Total, Cambio, ...) for the given year.

    Columns: Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.
    Alignment: left | right | right | right | center | right
    Sortable: True. Default sort: Indicador ASC (column 0).
    Sort types: text | text | text | text | text | number

    The Comp. column is rendered as a colored glyph:
      up   -> green triangle
      down -> red triangle
      flat -> gray "="

    Values (Ha 4 semanas / 1 sem / Hoje) are displayed as-is (preserve
    the source PT-BR format: "5,151%", "R$ 5,200").
    """
    columns = [
        "Indicador", "Ha 4 semanas", "1 sem", "Hoje", "Comp.", "Resp.",
    ]
    column_align = ["left", "right", "right", "right", "center", "right"]
    sort_types = ["text", "text", "text", "text", "text", "number"]

    rows: list[list] = []
    for obs in indicators:
        indicator = obs.get("indicator", "")
        row = [
            indicator,
            _value_numeric_cell(obs.get("four_weeks_ago"), indicator=indicator),
            _value_numeric_cell(obs.get("one_week_ago"), indicator=indicator),
            _value_numeric_cell(obs.get("today"), indicator=indicator),
            _comparison_cell(obs.get("comparison")),
            _respondents_cell(obs.get("respondents")),
        ]
        rows.append(row)

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": column_align,
        # Sortable-table feature (mirrors the ddm/acoes convention).
        "sortable":     True,
        "default_sort": {"column": 0, "direction": "asc"},
        "sort_types":   sort_types,
        "negative_red": True,
    }


def build_indicator_table(title: str, years_data: list[dict],
                          indicator: str = "",
                          window: str = "today",
                          description: str = "") -> dict:
    """Build the per-indicator years table.

    One row per year (2026, 2027, 2028, 2029) for the given indicator.
    Shows the value for the given time window (one of "four_weeks_ago",
    "one_week_ago", "today") in the main value column, plus the Comp.
    and Resp. columns from the latest "Hoje" snapshot.

    Columns: Ano | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.
    Alignment: right | right | right | right | center | right
    Sortable: True. Default sort: Ano ASC (column 0).
    Sort types: number | text | text | text | text | number

    Args:
        title:      Section title.
        years_data: List of observation dicts (one per year for this
                    indicator). Each dict has all 6 value fields.
        indicator:  Indicator name (for the description if needed).
        window:     Which time window to highlight (default "today").
                    The table shows ALL 3 windows side by side regardless,
                    so this param is currently informational only.
        description: Section description.
    """
    _ = window  # informational only - table always shows all 3 windows.
    columns = [
        "Ano", "Ha 4 semanas", "1 sem", "Hoje", "Comp.", "Resp.",
    ]
    column_align = ["right", "right", "right", "right", "center", "right"]
    sort_types = ["number", "text", "text", "text", "text", "number"]

    rows: list[list] = []
    for obs in years_data:
        year = obs.get("year", "")
        row = [
            str(year),
            _value_numeric_cell(obs.get("four_weeks_ago"), indicator=indicator),
            _value_numeric_cell(obs.get("one_week_ago"), indicator=indicator),
            _value_numeric_cell(obs.get("today"), indicator=indicator),
            _comparison_cell(obs.get("comparison")),
            _respondents_cell(obs.get("respondents")),
        ]
        rows.append(row)

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": column_align,
        "sortable":     True,
        "default_sort": {"column": 0, "direction": "asc"},
        "sort_types":   sort_types,
        "negative_red": True,
    }


def build_indicator_chart(title: str, years_data: list[dict],
                          indicator: str = "",
                          description: str = "") -> dict:
    """Build a grouped bar chart showing how expectations for ONE indicator
    evolved across years.

    3 datasets (one per time window):
      - "Ha 4 semanas" (teal)
      - "1 sem"        (amber)
      - "Hoje"         (blue)

    X-axis: years (2026, 2027, 2028, 2029).
    Y-axis: numeric value (parsed from PT-BR string).

    The chart makes it easy to see how market expectations for this
    indicator shifted over the past 4 weeks AND how they vary across
    target years (e.g. IPCA expectations for 2026 vs 2029).
    """
    # Sort years ascending (2026 -> 2029).
    sorted_data = sorted(
        [d for d in years_data if d.get("year") is not None],
        key=lambda d: d["year"],
    )
    labels = [str(d["year"]) for d in sorted_data]

    datasets = []
    for field_name in ("four_weeks_ago", "one_week_ago", "today"):
        color = _WINDOW_COLORS[field_name]
        label = _WINDOW_LABELS[field_name]
        data = []
        for d in sorted_data:
            parsed = parse_numeric(d.get(field_name))
            data.append(parsed)
        datasets.append({
            "label":           label,
            "data":            data,
            "backgroundColor": color,
            "borderColor":     color,
            "borderWidth":     1,
            "borderRadius":    3,
        })

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels":   labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {
                        "title": {"display": True, "text": "Ano"},
                    },
                    "y": {
                        "title": {"display": True, "text": "Valor"},
                        "beginAtZero": False,
                    },
                },
            },
        },
    }

