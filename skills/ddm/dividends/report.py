"""skills/ddm/dividends/report.py - Section builders for the dividends dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": "...", "value": "R$ 0,017250", "raw": <float>, "subtitle": ...}

  Dividends table (sortable):
    {"type": "table", "title": ..., "description": ...,
     "columns": ["Codigo", "Tipo", "Valor (R$)", "Registro", "Ex", "Pagamento"],
     "rows": [[...], ...], "column_align": [...],
     "sortable": True,
     "sort_types": ["text", "text", "number", "text", "text", "text"],
     "default_sort": {"column": 2, "direction": "desc"}}

  Distribution chart (grouped bar):
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type:"bar", data:{labels, datasets:[Dividendo, JCP]}}}

  Error section:
    {"type": "text", "title": ..., "body": "Erro ao consultar: ..."}

[v1] Sortable table feature (shipped in acoes commit):
  - section.sortable=True  -> macros.html emits th.sortable + onclick handlers
  - section.sort_types     -> "text" | "number" per column (read by JS)
  - section.default_sort   -> {"column": <int 0-indexed>, "direction": "asc"|"desc"}
  - Each Valor cell is a dict {"text": "R$ 0,017250", "data-value": "0.017250",
    "bg": "#fff3d6", "color": "#000"} so the macro can emit
    <td data-value="0.017250" style="background:#fff3d6;color:#000">R$ 0,017250</td>.
    The sortTable() JS reads data-value for numeric columns and textContent for
    text columns.
  - [v6] DPA colors applied to Valor cells (bg + color from
    skills/_colors/dpa.py — salmon -> pale yellow -> mint -> blue gradient).
  - Dates displayed as DD/MM/YYYY (PT-BR) but stored in DB as YYYY-MM-DD.
"""

from __future__ import annotations

from skills._base.kpi import build_kpi_card
from skills._base.error import build_error_section
from skills.ddm.dividends.helpers import format_brl, format_date, format_int


# Distribution chart value-range buckets (8 buckets).
# Each tuple: (label, lower_bound_inclusive, upper_bound_exclusive).
# Last bucket uses float('inf') as upper bound.
_DISTRIBUTION_BUCKETS = [
    ("<0,05",       0.00,   0.05),
    ("0,05-0,10",   0.05,   0.10),
    ("0,10-0,25",   0.10,   0.25),
    ("0,25-0,50",   0.25,   0.50),
    ("0,50-1,00",   0.50,   1.00),
    ("1,00-2,00",   1.00,   2.00),
    ("2,00-5,00",   2.00,   5.00),
    (">=5,00",      5.00,   float("inf")),
]

# Distribution chart colors (mirrors the user spec):
#   Dividendo = teal #0d9488
#   JCP       = amber #f59e0b
_COLOR_DIVIDENDO = "#0d9488"
_COLOR_JCP = "#f59e0b"


def build_dividends_table(title: str, dividends: list[dict],
                          description: str = "") -> dict:
    """Build a sortable dividends table.

    Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento

    Args:
        title:       Table title.
        dividends:   List of {ticker, tipo, value, record_date, ex_date,
                              payment_date} dicts.
        description: Optional description shown above the table.

    Sortable table contract (shipped in acoes commit - macros.html + base.html
    + dashboard.html):
      - sortable=True               -> headers get class "sortable" + onclick
      - sort_types                  -> per-column "text" | "number" hint
      - default_sort                -> {column, direction} to apply on load
      - Numeric cells are dicts {"text", "data-value", "bg", "color"} so the
        macro can emit <td data-value="0.017250" style="background:#fff3d6;color:#000">R$ 0,017250</td>.
        Text cells are plain strings.

    [v6] DPA colors on Valor (bg + color from skills/_colors/dpa.py —
    salmon -> pale yellow -> mint -> blue gradient for dividend-per-share
    amounts).
    Dates are displayed as DD/MM/YYYY (PT-BR).
    """
    # Lazy import to avoid loading skills._colors.dpa when this module is
    # imported (keeps the skill importable in standalone mode).
    from skills._colors.dpa import dpa_range_color

    rows = []
    for d in dividends:
        value = d.get("value")
        # Numeric cell: dict so the macro can emit data-value attribute.
        if value is None:
            value_cell: dict | str = {"text": "-", "data-value": ""}
        else:
            try:
                # [v6] Apply DPA-range color (bg + text color) to the Valor cell.
                dpa_color = dpa_range_color(float(value))
                value_cell = {
                    "text":       format_brl(value),
                    "data-value": f"{float(value):.6f}",
                    "bg":         dpa_color.get("bg", ""),
                    "color":      dpa_color.get("color", ""),
                }
            except (ValueError, TypeError):
                value_cell = {"text": str(value), "data-value": ""}

        # [v5] Color the Tipo cell: Dividendo = teal, JCP = amber
        tipo_raw = (d.get("tipo", "") or "").strip()
        if tipo_raw.upper() == "JCP":
            tipo_cell = {"text": tipo_raw, "color": "#f59e0b"}
        else:
            tipo_cell = {"text": tipo_raw, "color": "#0d9488"}

        rows.append([
            d.get("ticker", ""),
            tipo_cell,
            value_cell,
            format_date(d.get("record_date", "")),
            format_date(d.get("ex_date", "")),
            format_date(d.get("payment_date", "")),
        ])

    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      [
            "Codigo", "Tipo", "Valor (R$)",
            "Registro", "Ex", "Pagamento",
        ],
        "rows":         rows,
        "column_align": ["left", "left", "right", "right", "right", "right"],
        # Sortable table feature (shipped in acoes commit):
        "sortable":     True,
        "sort_types":   ["text", "text", "number", "text", "text", "text"],
        "default_sort": {"column": 2, "direction": "desc"},
        # NOTE: NO negative_red, NO price-color logic at the table level - the
        # per-cell bg/color on Valor comes from the DPA range color scheme
        # (skills/_colors/dpa.py). Dividend amounts are always >= 0, so
        # negative_red is meaningless here.
    }


def build_distribution_chart(title: str, dividends: list[dict],
                             description: str = "") -> dict:
    """Build a grouped bar chart of dividend count per value range.

    2 datasets (side-by-side bars, NOT stacked):
      - Dividendo (teal #0d9488)
      - JCP       (amber #f59e0b)

    8 value-range buckets on the X-axis:
      <0,05 | 0,05-0,10 | 0,10-0,25 | 0,25-0,50 |
      0,50-1,00 | 1,00-2,00 | 2,00-5,00 | >=5,00

    Y-axis: count of dividends in each bucket.

    Args:
        title:       Chart title.
        dividends:   List of {ticker, tipo, value, ...} dicts.
        description: Optional description.
    """
    labels = [b[0] for b in _DISTRIBUTION_BUCKETS]
    dividendo_counts = [0] * len(_DISTRIBUTION_BUCKETS)
    jcp_counts = [0] * len(_DISTRIBUTION_BUCKETS)

    for d in dividends:
        v = d.get("value")
        if v is None:
            continue
        try:
            v_f = float(v)
        except (ValueError, TypeError):
            continue
        # Find the bucket: lower <= v < upper. Last bucket is unbounded.
        for i, (_, lo, hi) in enumerate(_DISTRIBUTION_BUCKETS):
            if lo <= v_f < hi:
                if (d.get("tipo") or "").strip().upper() == "JCP":
                    jcp_counts[i] += 1
                else:
                    dividendo_counts[i] += 1
                break

    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "type":            "bar",
                        "label":           "Dividendo",
                        "data":            dividendo_counts,
                        "backgroundColor": _COLOR_DIVIDENDO,
                        "borderColor":     _COLOR_DIVIDENDO,
                        "borderWidth":     0,
                    },
                    {
                        "type":            "bar",
                        "label":           "JCP",
                        "data":            jcp_counts,
                        "backgroundColor": _COLOR_JCP,
                        "borderColor":     _COLOR_JCP,
                        "borderWidth":     0,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"title": {"display": True, "text": "Faixa de valor (R$)"}},
                    "y": {"title": {"display": True, "text": "Quantidade de dividendos"},
                          "beginAtZero": True,
                          "ticks": {"precision": 0}},
                },
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


# Helper: expose format_int so the dashboard mode can format count KPIs.
def _format_count(v) -> str:
    """Format an integer count using PT-BR thousands separators."""
    return format_int(v)
