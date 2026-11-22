"""skills/ddm/acoes/report.py - Section builders for the acoes dashboard.

[v1] Sortable table + price distribution chart:
  - build_stocks_table: emits a SORTABLE table:
      * sortable: True (enables JS sortTable() in base.html)
      * default_sort: {"column": 2, "direction": "desc"} (Negócios DESC)
      * sort_types: ["text", "text", "number", "number", "number"]
      * Each numeric cell is a dict {"text": <display>, "data-value": <raw>}
        so the JS sorter can read the raw numeric value via getAttribute.
  - build_distribution_chart: Chart.js bar chart with 22 colored bars (one
      per price-range bucket from skills/_colors/price.py — the palette
      grew from 16 to 22 ranges in its v2, adding the 100–300+ blue tail).
      The bars' colors match the price-range palette exactly (red -> pink
      -> yellow -> green -> teal -> blue).

[v2] Evolution sections — the distribution OVER TIME (the /acoes page is
a live quote table with NO history, so the series comes from the
stocks_history snapshots accumulated by every sync — see
sync_engine.py):
  - build_evolution_sections: TWO Chart.js stacked-area charts over the
      snapshot dates — the % of total per range (100% stacked, the
      reference chart style) and the absolute count per range — one
      dataset per range in the palette's color, lowest prices at the
      bottom. Tooltips use interaction mode 'nearest' (a 22-band index
      tooltip would be a wall); both carry the Tudo/10A/.../1M range
      selector. Fewer than 2 snapshots degrade to a text note (the
      history starts accumulating with the syncs).

The macros.html `data_table` macro detects `sortable=True` on the section
and renders <th onclick="sortTable(this, N)" data-sort-type="number|text">
+ a sort indicator (arrow) on the default-sorted column.
"""
from __future__ import annotations

from skills._base.kpi import build_kpi_card
from skills._base.error import build_error_section
from skills.ddm.acoes.helpers import (
    format_brl, format_int, format_pct, distribution_snapshots,
)


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

    Columns: Ticker | Nome | Negócios | Última (R$) | Variação
    Alignment: left | left | right | right | right
    Sortable: True (click headers to sort asc/desc)
    Default sort: column 2 (Negócios) DESC
    Sort types: text | text | number | number | number
    Negative variation values render in red (negative_red=True).

    Each numeric cell carries a `data-value` attribute with the raw float /
    int, so the JS sorter doesn't have to parse "R$ 44,30" or "+2,78%".
    Variation cells include a sign in the display text (+2,78% / -10,85%).
    """
    columns = ["Ticker", "Nome", "Negócios", "Última (R$)", "Variação"]
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
        from skills._colors.price import price_range_color
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

    Uses ``skills._colors.price.price_distribution`` to bucket each price
    into one of 22 ranges (red -> pink -> yellow -> green -> teal -> blue —
    the palette's v2 added the 100–300+ blue tail on top of the original
    16). Each bar gets its range's color so the chart is a single-glance
    view of where B3 prices cluster (most stocks trade below R$50).

    Args:
        title:       Section + chart title.
        prices:      List of last_price floats (None entries are skipped).
        description: Optional description shown above the chart.

    Returns:
        Chart section dict with Chart.js bar config in ``chart_data``.
    """
    # Lazy import to avoid loading skills._colors.price when this module
    # is imported (keeps the skill importable in standalone mode).
    from skills._colors.price import price_distribution

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
                    "label":           "Número de Ações",
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
                        "title": {"display": True, "text": "Faixa de Preço (R$)"},
                        "ticks": {"maxRotation": 45, "minRotation": 30},
                    },
                    "y": {
                        "title": {"display": True, "text": "Número de Ações"},
                        "beginAtZero": True,
                        "ticks": {"precision": 0},
                    },
                },
            },
        },
    }


def _evolution_datasets(snap: dict, series: list[list]) -> list[dict]:
    """One filled dataset per price range, lowest prices first.

    ``series`` is indexed [date][range] (the distribution_snapshots
    shape); Chart.js needs [range][date] (one dataset per range across
    dates), so it is transposed here. Chart.js stacks dataset 0 at the
    BOTTOM, so the palette order (lowest range first) puts the red/pink
    low-price bands at the bottom — the reference chart's layout.
    """
    n_ranges = len(snap["ranges"])
    by_range = [
        [day[r] for day in series] for r in range(n_ranges)
    ]
    return [
        {
            "label":            rng["label"],
            "data":             row,
            "backgroundColor":  rng["color"],
            "borderColor":      rng["color"],
            "borderWidth":      0,
            "fill":             True,
            "pointRadius":      0,
            "pointHoverRadius": 3,
            "tension":          0.2,
        }
        for rng, row in zip(snap["ranges"], by_range)
    ]


def build_evolution_sections(dates: list[str],
                             prices_by_date: list[list],
                             description: str = "") -> list[dict]:
    """Build the TWO distribution-over-time chart sections (v2).

    The star chart is the 100% stacked area — each band is a price range
    in the palette's color, each column a stored snapshot, and the bands
    sum to exactly 100% on every date (the reference chart style). The
    second chart stacks the ABSOLUTE counts (the total is the number of
    listed stocks on each date — delistings show as a shrinking top).

    Args:
        dates:          snapshot dates ASC (ISO YYYY-MM-DD — the range
                        selector + the date-axis formatting read ISO).
        prices_by_date: per-date list of last_price floats.
        description:    Shared lead-in for both chart descriptions.

    Returns:
        [chart_section (% do total), chart_section (nº de ações)].
    """
    snap = distribution_snapshots(dates, prices_by_date)

    def _pct_chart() -> dict:
        title = "Evolução da Distribuição — % do Total"
        datasets = _evolution_datasets(snap, snap["shares"])
        return {
            "type":        "chart",
            "title":       title,
            "description": (
                (description + " " if description else "")
                + "A fatia de cada faixa de preço no total de ações, um "
                "ponto por snapshot diário — as faixas somam 100% em "
                "cada data (área 100% empilhada; as faixas baixas ficam "
                "embaixo, vermelho/rosa → amarelo/verde → azul). Passe o "
                "mouse para ler a faixa mais próxima; use a barra de "
                "período para filtrar."
            ),
            "chart_data": {
                "type": "line",
                "data": {"labels": list(dates), "datasets": datasets},
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "nearest", "intersect": False},
                    "plugins": {
                        "title":  {"display": True, "text": title},
                        "legend": {"display": True, "position": "right"},
                    },
                    "scales": {
                        "x": {"stacked": True, "ticks": {"maxTicksLimit": 12}},
                        "y": {
                            "stacked": True,
                            "max": 100,
                            "title": {"display": True, "text": "% do total"},
                        },
                    },
                },
            },
            "price_range_selector": True,
            "price_full_labels":    list(dates),
            "price_full_datasets":  [{"data": ds["data"], "label": ds["label"]}
                                     for ds in datasets],
        }

    def _abs_chart() -> dict:
        title = "Evolução da Distribuição — Nº de Ações"
        datasets = _evolution_datasets(snap, snap["counts"])
        return {
            "type":        "chart",
            "title":       title,
            "description": (
                "O número de ações em cada faixa ao longo do tempo (área "
                "empilhada) — a visão absoluta do mesmo histórico: a "
                "altura total é o número de ações listadas em cada data "
                "(deslistagens encolhem o topo)."
            ),
            "chart_data": {
                "type": "line",
                "data": {"labels": list(dates), "datasets": datasets},
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "nearest", "intersect": False},
                    "plugins": {
                        "title":  {"display": True, "text": title},
                        "legend": {"display": True, "position": "right"},
                    },
                    "scales": {
                        "x": {"stacked": True, "ticks": {"maxTicksLimit": 12}},
                        "y": {
                            "stacked": True,
                            "beginAtZero": True,
                            "title": {"display": True, "text": "Número de ações"},
                        },
                    },
                },
            },
            "price_range_selector": True,
            "price_full_labels":    list(dates),
            "price_full_datasets":  [{"data": ds["data"], "label": ds["label"]}
                                     for ds in datasets],
        }

    return [_pct_chart(), _abs_chart()]


def build_history_note_section(n_snapshots: int, ref_date: str = "") -> dict:
    """The graceful-degradation note when the evolution can't chart yet.

    Fewer than 2 stored snapshots → instead of a one-column area chart,
    a text section explains HOW the history accumulates (one snapshot per
    sync, keyed by day — re-syncing the same day replaces, a new day
    adds; the first sync after the v2 upgrade also preserves the previous
    `stocks` snapshot).
    """
    when = f" (snapshot atual: {ref_date})" if ref_date else ""
    if n_snapshots <= 0:
        body = (
            "O histórico evolutivo ainda não tem snapshots armazenados. "
            "Cada sincronização da fonte ddm-acoes guarda o snapshot do "
            "dia em stocks_history — a partir do próximo sync a evolução "
            "da distribuição de preços passa a ser exibida aqui"
            + when + "."
        )
    else:
        body = (
            f"O histórico evolutivo tem {n_snapshots} snapshot"
            + ("s" if n_snapshots != 1 else "")
            + " armazenado" + ("s" if n_snapshots != 1 else "")
            + when + ". A evolução ganha forma a cada sincronização — "
            "sincronize em dias diferentes para acumular um ponto por dia "
            "(re-sincronizar no mesmo dia substitui o snapshot do dia)."
        )
    return {"type": "text", "title": "Evolução da Distribuição de Preços",
            "text": body}

