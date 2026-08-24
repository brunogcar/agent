"""skills/ddm/fluxo/report.py - Section builders for the fluxo dashboard.

[v1] 8 builders:

  - build_kpi_card(label, value, subtitle):
      Top-level KPI card.

  - build_fluxo_table(title, observations, description):
      Sortable table with ALL investor columns + all dates.
      Columns: Data | Estrangeiro | Institucional | Pessoa fisica |
               Inst. Financeira | Outros
      Alignment: left | right | right | right | right | right
      Sortable: True. Default sort: Data DESC (column 0, newest first).
      Sort types: text | number | number | number | number | number
      negative_red: True (negative cells render in red).

  - build_fluxo_chart(title, observations, description):
      Daily bar chart with 4 datasets (Estrangeiro, Institucional,
      Pessoa fisica, Inst. Financeira). Range selector enabled.

  - build_investor_daily_chart(title, investor, observations, description):
      Daily bar chart for ONE investor. Green for positive days, red
      for negative. Range selector enabled.

  - build_investor_monthly_chart(title, monthly_data, description):
      Monthly cumulative line chart. Green for positive months, red
      for negative.

  - build_investor_annual_chart(title, cumulative_data, description):
      Running annual cumulative line chart (green line). Range selector.

  - build_investor_table(title, observations, investor, description):
      Sortable table with 2 columns (Data | Valor (mi)).
      Default sort: Data DESC.
      negative_red: True.

  - build_error_section(title, error):
      Plain text section for error messages.

Section titles don't repeat the investor (already in tab name).
"""
from __future__ import annotations

from skills._base.kpi import build_kpi_card
from skills._base.error import build_error_section
from skills.ddm.fluxo.helpers import (
    format_brl, format_date,
)


# Chart palette for the 4 investors in the Fluxo tab:
#   - Estrangeiro     -> blue   (typically the largest outflow)
#   - Institucional   -> red
#   - Pessoa fisica   -> amber
#   - Inst. Financeira -> green
_INVESTOR_COLORS = {
    "estrangeiro":     "#3b82f6",  # blue-500
    "institucional":   "#ef4444",  # red-500
    "pessoa_fisica":   "#f59e0b",  # amber-500
    "inst_financeira": "#22c55e",  # green-500
}

_INVESTOR_LABELS = {
    "estrangeiro":     "Estrangeiro",
    "institucional":   "Institucional",
    "pessoa_fisica":   "Pessoa fisica",
    "inst_financeira": "Inst. Financeira",
}

# Cell colors for positive/negative values.
_POSITIVE_COLOR = "#22c55e"  # green-500
_NEGATIVE_COLOR = "#ef4444"  # red-500
# [v4] Color for line segments that CROSS zero (pos→neg or neg→pos).
# Yellow-500: clearly distinct from green/red and from the amber used for
# Pessoa fisica bars (#f59e0b).


def _value_cell(value) -> dict:
    """Build a value cell with text + data-value + red color for negatives.

    The cell text uses PT-BR format ("R$ -1.582,35 mi") for display,
    while the data-value attribute carries the raw float for accurate
    numeric sorting (so -1582.35 sorts before -9.31, not after).

    [v3] Negative values set cell["color"] = red explicitly. The shared
    table template detects negatives via ``cell_text.startswith('-')``,
    but format_brl produces "R$ -1.582,35 mi" (starts with "R$ ", not
    "-"), so the template's own detection misses them. Setting
    ``cell["color"]`` makes the template apply ``color: <color>`` via
    its ``cell_color`` branch — works regardless of the text prefix.
    """
    text = format_brl(value)
    cell: dict = {"text": text}
    if value is not None:
        try:
            fval = float(value)
            cell["data-value"] = f"{fval:.6f}"
            if fval < 0:
                cell["color"] = _NEGATIVE_COLOR
        except (ValueError, TypeError):
            pass
    return cell


def _date_cell(value) -> dict:
    """Build a date cell with text (DD/MM/YYYY) + data-value (YYYY-MM-DD).

    The data-value attribute carries the ISO date so the JS sorter sorts
    dates chronologically (not lexicographically on DD/MM/YYYY).
    """
    text = format_date(value)
    cell: dict = {"text": text}
    if value:
        cell["data-value"] = str(value)
    return cell


def build_fluxo_table(title: str, observations: list[dict],
                      description: str = "") -> dict:
    """Build the sortable fluxo table with ALL investor columns.

    One row per ref_date. The dashboard passes observations in ASC order
    (oldest first); the table's default_sort = column 0 DESC means the
    user sees the newest dates first.

    Columns: Data | Estrangeiro | Institucional | Pessoa fisica |
             Inst. Financeira | Outros
    Alignment: left | right | right | right | right | right
    Sortable: True. Default sort: Data DESC (column 0).
    Sort types: text | number | number | number | number | number
    negative_red: True (negative cells render in red).
    Dates displayed as DD/MM/YYYY.
    """
    columns = [
        "Data", "Estrangeiro", "Institucional", "Pessoa fisica",
        "Inst. Financeira", "Outros",
    ]
    column_align = ["left", "right", "right", "right", "right", "right"]
    sort_types = ["text", "number", "number", "number", "number", "number"]

    rows: list[list] = []
    for obs in observations:
        row = [
            _date_cell(obs.get("ref_date")),
            _value_cell(obs.get("estrangeiro")),
            _value_cell(obs.get("institucional")),
            _value_cell(obs.get("pessoa_fisica")),
            _value_cell(obs.get("inst_financeira")),
            _value_cell(obs.get("outros")),
        ]
        rows.append(row)

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": column_align,
        # Sortable-table feature.
        "sortable":     True,
        "default_sort": {"column": 0, "direction": "desc"},
        "sort_types":   sort_types,
        # Negative values render in red.
        "negative_red": True,
    }


def build_fluxo_chart(title: str, observations: list[dict],
                      description: str = "") -> dict:
    """Build a daily OVERLAPPING bar chart with 4 investor datasets.

    [v3] All 4 datasets render from the SAME zero baseline and overlap
    at each date (matching the reference chart in Fluxo.png), instead of
    being grouped side-by-side. This is achieved by binding each dataset
    to its own (hidden) x-axis so Chart.js places every bar at the same
    category position rather than splitting the slot into 4 thin grouped
    bars.

    Datasets (render order → last is on top):
      - Estrangeiro      (blue)   → x
      - Institucional    (red)    → x2
      - Pessoa fisica    (amber)  → x3
      - Inst. Financeira (green)  → x4

    X-axis: dates (DD/MM/YYYY). Y-axis: millions R$.
    Range selector enabled (Tudo/10A/5A/1A/6M/3M/1M).

    Note: x2/x3/x4 have no explicit ``labels`` so they inherit
    ``chart.data.labels`` — this lets filterPriceChart update all 4
    axes in lock-step by only touching chart.data.labels.
    """
    # Sort observations ASC by date so the chart shows time in order.
    sorted_obs = sorted(
        [o for o in observations if o.get("ref_date")],
        key=lambda o: o["ref_date"],
    )
    labels = [format_date(o["ref_date"]) for o in sorted_obs]

    # One hidden x-axis per dataset so bars overlap (not group).
    _x_axes = ("x", "x2", "x3", "x4")
    datasets = []
    for i, field in enumerate(("estrangeiro", "institucional",
                              "pessoa_fisica", "inst_financeira")):
        color = _INVESTOR_COLORS[field]
        label = _INVESTOR_LABELS[field]
        data = [o.get(field) for o in sorted_obs]
        datasets.append({
            "label":           label,
            "data":            data,
            "backgroundColor": color,
            "borderColor":     color,
            "borderWidth":     1,
            "borderRadius":    2,
            "xAxisID":         _x_axes[i],
        })

    # Shared bar/category sizing — identical on all 4 axes so bars
    # fully overlap (same width, same position).
    _bar_cfg = {"barPercentage": 0.9, "categoryPercentage": 1.0,
                "stacked": False}

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
                    # Displayed x-axis (dates).
                    "x": {
                        "display": True,
                        "title": {"display": True, "text": "Data"},
                        "ticks": {"maxTicksLimit": 15},
                        **_bar_cfg,
                    },
                    # Hidden axes — no ``labels`` key → inherit
                    # chart.data.labels (kept in sync by range selector).
                    "x2": {"display": False, "offset": True, **_bar_cfg},
                    "x3": {"display": False, "offset": True, **_bar_cfg},
                    "x4": {"display": False, "offset": True, **_bar_cfg},
                    "y": {
                        "title": {"display": True, "text": "Milhoes R$"},
                        "beginAtZero": False,
                        "stacked": False,
                    },
                },
            },
        },
        # Range selector (Tudo/10A/5A/1A/6M/3M/1M).
        # The template's filterPriceChart JS requires all 3 keys.
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": ds["data"], "label": ds["label"]} for ds in datasets
        ],
    }


def build_investor_daily_chart(title: str, investor: str,
                               observations: list[dict],
                               description: str = "") -> dict:
    """Build a daily bar chart for ONE investor.

    Single dataset with green bars for positive days and red bars for
    negative days. The per-bar color is set via the `backgroundColor`
    array (one color per data point).

    X-axis: dates (DD/MM/YYYY). Y-axis: millions R$.
    Range selector enabled.

    Args:
        title:        Chart + section title.
        investor:     Investor column name ("estrangeiro" / "institucional"
                      / "pessoa_fisica" / "inst_financeira"). Used for the
                      dataset label + display.
        observations: List of {"ref_date", "value"} dicts (daily flow).
        description:  Optional description above the chart.
    """
    sorted_obs = sorted(
        [o for o in observations if o.get("ref_date") is not None],
        key=lambda o: o["ref_date"],
    )
    labels = [format_date(o["ref_date"]) for o in sorted_obs]
    data = [o.get("value") for o in sorted_obs]
    # Per-bar colors: green for positive (or zero), red for negative.
    bg_colors = [
        _POSITIVE_COLOR if (v is not None and v >= 0) else _NEGATIVE_COLOR
        for v in data
    ]
    label = _INVESTOR_LABELS.get(investor, investor)

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels":   labels,
                "datasets": [{
                    "label":           label,
                    "data":            data,
                    "backgroundColor": bg_colors,
                    "borderColor":     bg_colors,
                    "borderWidth":     1,
                    "borderRadius":    2,
                }],
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
                        "title": {"display": True, "text": "Data"},
                        "ticks": {"maxTicksLimit": 15},
                    },
                    "y": {
                        "title": {"display": True, "text": "Milhoes R$"},
                        "beginAtZero": False,
                    },
                },
            },
        },
        # Range selector (Tudo/10A/5A/1A/6M/3M/1M).
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": data, "label": label},
        ],
    }


def build_investor_monthly_chart(title: str, monthly_data: list[dict],
                                 description: str = "") -> dict:
    """Build a monthly cumulative line chart for ONE investor.

    Single line dataset. Each data point is the SUM of daily values in
    that month. [v3] The line SEGMENT turns red when either endpoint is
    negative (matching the reference chart in Mensal.png) — achieved via
    the ``_segment_negative_red`` flag, which the dashboard template
    turns into a Chart.js ``segment.borderColor`` callback (the JSON
    clone in _renderChart strips functions, so the template injects
    this callback post-clone based on the flag).

    Points are also colored green/red per-sign for consistency.

    X-axis: month labels (Jan/2026, Fev/2026, etc.).
    Y-axis: millions R$.

    Args:
        title:        Chart + section title.
        monthly_data: List of {"month": "2026-08", "label": "Ago/2026",
                      "value": <float>} dicts (monthly cumulative sums).
        description:  Optional description above the chart.
    """
    sorted_data = sorted(
        [d for d in monthly_data if d.get("month")],
        key=lambda d: d["month"],
    )
    labels = [d.get("label") or d["month"] for d in sorted_data]
    data = [d.get("value") for d in sorted_data]
    # Per-point colors: green for positive, red for negative.
    point_colors = [
        _POSITIVE_COLOR if (v is not None and v >= 0) else _NEGATIVE_COLOR
        for v in data
    ]

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {
                "labels":   labels,
                "datasets": [{
                    "label":           "Mensal acumulado",
                    "data":            data,
                    "borderColor":     _POSITIVE_COLOR,
                    "backgroundColor": _POSITIVE_COLOR,
                    "pointBackgroundColor": point_colors,
                    "pointBorderColor":     point_colors,
                    "fill":     False,
                    "tension":  0.3,
                    "borderWidth": 2,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                # [v3/v4] Flags consumed by _applySegmentColors in the
                # dashboard template: injects segment.borderColor callback
                # that paints each segment based on endpoint signs:
                #   pos→pos=green, neg→neg=red, crossing=yellow.
                "_segment_negative_red": True,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {
                        "title": {"display": True, "text": "Mes"},
                        "ticks": {"maxTicksLimit": 12},
                    },
                    "y": {
                        "title": {"display": True, "text": "Milhoes R$"},
                        "beginAtZero": False,
                    },
                },
            },
        },
    }


def build_investor_annual_chart(title: str, cumulative_data: list[dict],
                                description: str = "") -> dict:
    """Build a running annual cumulative line chart for ONE investor.

    Each day's value = the running total of the investor's flow from the
    first day in the DB to that day. [v3] The line SEGMENT turns red
    when either endpoint dips below zero (matching the reference chart
    in Anual.png — a brief red dip during a negative period) via the
    ``_segment_negative_red`` flag (see build_investor_monthly_chart for
    the mechanism). Points are also colored per-sign.

    X-axis: dates (DD/MM/YYYY). Y-axis: millions R$ (running cumulative).
    Range selector enabled.

    Args:
        title:           Chart + section title.
        cumulative_data: List of {"ref_date": <str>, "value": <float>} dicts
                         (running cumulative sum).
        description:     Optional description above the chart.
    """
    sorted_data = sorted(
        [d for d in cumulative_data if d.get("ref_date")],
        key=lambda d: d["ref_date"],
    )
    labels = [format_date(d["ref_date"]) for d in sorted_data]
    data = [d.get("value") for d in sorted_data]
    # Per-point colors: green for positive, red for negative.
    point_colors = [
        _POSITIVE_COLOR if (v is not None and v >= 0) else _NEGATIVE_COLOR
        for v in data
    ]

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {
                "labels":   labels,
                "datasets": [{
                    "label":           "Acumulado anual",
                    "data":            data,
                    "borderColor":     _POSITIVE_COLOR,
                    "backgroundColor": _POSITIVE_COLOR,
                    "pointBackgroundColor": point_colors,
                    "pointBorderColor":     point_colors,
                    "fill":     False,
                    "tension":  0.3,
                    "borderWidth": 2,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                # [v3/v4] Flags consumed by _applySegmentColors in the
                # dashboard template (see build_investor_monthly_chart).
                "_segment_negative_red": True,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
                "scales": {
                    "x": {
                        "title": {"display": True, "text": "Data"},
                        "ticks": {"maxTicksLimit": 15},
                    },
                    "y": {
                        "title": {"display": True,
                                  "text": "Milhoes R$ (acumulado)"},
                        "beginAtZero": False,
                    },
                },
            },
        },
        # Range selector (Tudo/10A/5A/1A/6M/3M/1M).
        "price_range_selector": True,
        "price_full_labels":    labels,
        "price_full_datasets":  [
            {"data": data, "label": "Acumulado anual"},
        ],
    }


def build_investor_table(title: str, observations: list[dict],
                         investor: str = "", description: str = "") -> dict:
    """Build the sortable per-investor daily table.

    Columns: Data | Valor (mi)
    Alignment: left | right
    Sortable: True. Default sort: Data DESC (column 0).
    Sort types: text | number
    negative_red: True.

    Args:
        title:        Section title.
        observations: List of {"ref_date", "value"} dicts.
        investor:     Investor column name (for description context).
        description:  Optional section description.
    """
    _ = investor  # informational only - column header is generic.
    columns = ["Data", "Valor (mi)"]
    column_align = ["left", "right"]
    sort_types = ["text", "number"]

    rows: list[list] = []
    for obs in observations:
        row = [
            _date_cell(obs.get("ref_date")),
            _value_cell(obs.get("value")),
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
        "default_sort": {"column": 0, "direction": "desc"},
        "sort_types":   sort_types,
        "negative_red": True,
    }
