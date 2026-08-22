"""skills/ddm/acoes/report.py - Section builders for the acoes dashboard.

[v1] Sortable table + price distribution chart:
  - build_stocks_table: emits a SORTABLE table:
      * sortable: True (enables JS sortTable() in base.html)
      * default_sort: {"column": 2, "direction": "desc"} (Negocios DESC)
      * sort_types: ["text", "text", "number", "number", "number"]
      * Each numeric cell is a dict {"text": <display>, "data-value": <raw>}
        so the JS sorter can read the raw numeric value via getAttribute.
  - build_distribution_chart: Chart.js bar chart with 16 colored bars (one
      per price-range bucket from skills/_price_colors.py). The bars' colors
      match the price-range palette exactly (red -> pink -> yellow -> green
      -> teal -> blue).

The macros.html `data_table` macro detects `sortable=True` on the section
and renders <th onclick="sortTable(this, N)" data-sort-type="number|text">
+ a sort indicator (arrow) on the default-sorted column.
"""
from __future__ import annotations

from skills.ddm.acoes.helpers import (
    format_brl, format_int, format_pct,
)


def build_kpi_card(label: str, value, subtitle: str = "",
                   formatted: str = "") -> dict:
    """Build a KPI card.

    Args:
        label:     KPI label (e.g. "Total de Acoes").
        value:     Raw value (number / string).
        subtitle:  Optional subtitle / context.
        formatted: Pre-formatted display value (overrides format_value).
                   Useful when value is already a string like "PETR4".
    """
    if formatted:
        display = formatted
    elif isinstance(value, (int, float)):
        display = format_int(value)
    else:
        display = str(value) if value is not None else "-"

    return {
        "label":    label,
        "value":    display,
        "raw":      value,
        "subtitle": subtitle,
    }


def _cell(text: str, data_value: str = "", bg: str = "", color_override: str = "") -> dict:
    """Build a table cell with optional data-value + background color.

    The data-value attribute is used by the JS sortTable() function to
    sort numeric columns accurately even when the displayed text has
    formatting (R$ prefix, % suffix, thousands separators).
    """
    cell = {"text": text}
    if data_value:
        cell["data-value"] = data_value
    if bg:
        cell["bg"] = bg
    if color_override:
        cell["color"] = color_override
    return cell


def build_stocks_table(title: str, stocks: list[dict],
                       description: str = "") -> dict:
    """Build the sortable stocks table.

    Columns: Ticker | Nome | Negocios | Ultima (R$) | Variacao
    Alignment: left | left | right | right | right
    Sortable: True (click headers to sort asc/desc)
    Default sort: column 2 (Negocios) DESC
    Sort types: text | text | number | number | number
    Negative variation values render in red (negative_red=True).

    Each numeric cell carries a `data-value` attribute with the raw float /
    int, so the JS sorter doesn't have to parse "R$ 44,30" or "+2,78%".
    Variation cells include a sign in the display text (+2,78% / -10,85%).
    """
    columns = ["Ticker", "Nome", "Negocios", "Valor", "Variacao"]
    column_align = ["left", "left", "right", "right", "right"]
    sort_types = ["text", "text", "number", "number", "number"]

    rows: list[list] = []
    for s in stocks:
        ticker = s.get("ticker", "")
        name = s.get("name", "") or ""
        negocios = s.get("negocios")
        last_price = s.get("last_price")
        variation = s.get("variation")

        # Numeric cells: dict with text + data-value for accurate sorting.
        negocios_cell = _cell(
            format_int(negocios),
            data_value=str(negocios) if negocios is not None else "0",
        )
        # [v2] Apply price-range color to the Valor cell
        from skills._price_colors import price_range_color
        price_color = price_range_color(last_price) if last_price is not None else {"bg": "", "color": ""}
        price_cell = _cell(
            format_brl(last_price),
            data_value=f"{last_price:.6f}" if last_price is not None else "0",
            bg=price_color.get("bg", ""),
            color_override=price_color.get("color", ""),
        )
        variation_cell = _cell(
            format_pct(variation),
            data_value=f"{variation:.6f}" if variation is not None else "0",
        )

        rows.append([ticker, name, negocios_cell, price_cell, variation_cell])

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      columns,
        "rows":         rows,
        "column_align": column_align,
        "negative_red": True,
        # Sortable-table feature (new in v1):
        #   sortable=True enables JS sortTable() on click of <th>.
        #   default_sort tells the macro which column starts sorted.
        #   column index is 0-based (Negocios = index 2).
        #   sort_types tells the macro the per-column sort algorithm
        #   ("text" = lexicographic, "number" = numeric via data-value).
        "sortable":     True,
        "default_sort": {"column": 2, "direction": "desc"},
        "sort_types":   sort_types,
    }


def build_distribution_chart(title: str, prices: list[float | None],
                             description: str = "") -> dict:
    """Build a column chart of the price-range distribution.

    Uses ``skills._price_colors.price_distribution`` to bucket each price
    into one of 16 ranges (red -> pink -> yellow -> green -> teal -> blue).
    Each bar gets its range's color so the chart is a single-glance view
    of where B3 prices cluster (most stocks trade below R$50).

    Args:
        title:       Section + chart title.
        prices:      List of last_price floats (None entries are skipped).
        description: Optional description shown above the chart.

    Returns:
        Chart section dict with Chart.js bar config in ``chart_data``.
    """
    # Lazy import to avoid loading skills._price_colors when this module
    # is imported (keeps the skill importable in standalone mode).
    from skills._price_colors import price_distribution

    buckets = price_distribution(prices)
    labels = [b["range"] for b in buckets]
    counts = [b["count"] for b in buckets]
    bg_colors = [b["color"] for b in buckets]
    # Bar border = same as fill (so the bar appears solid).
    border_colors = list(bg_colors)

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label":           "Numero de Acoes",
                    "data":            counts,
                    "backgroundColor": bg_colors,
                    "borderColor":     border_colors,
                    "borderWidth":     1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": False},
                },
                "scales": {
                    "x": {
                        "title": {"display": True, "text": "Faixa de Preco (R$)"},
                        "ticks": {"maxRotation": 45, "minRotation": 30},
                    },
                    "y": {
                        "title": {"display": True, "text": "Numero de Acoes"},
                        "beginAtZero": True,
                        "ticks": {"precision": 0},
                    },
                },
            },
        },
    }


def build_error_section(title: str, error: str) -> dict:
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
