"""skills/ddm/dividends/report.py - Section builders for the Proventos dashboard.

Each builder returns a dict shaped for the report tool's build_dashboard()
+ the dashboard.html template:

  KPI card (top-level only):
    {"label": "...", "value": "R$ 0,017250", "raw": <float>, "subtitle": ...}

  Agenda table (sortable):
    {"type": "table", "title": ..., "description": ...,
     "columns": ["Código", "Tipo", "Valor (R$)", "Registro", "Ex", "Pagamento"],
     "rows": [[...], ...], "column_align": [...],
     "sortable": True,
     "sort_types": ["text", "text", "number", "text", "text", "text"],
     "default_sort": {"column": 2, "direction": "desc"}}

  Distribution chart (grouped bar):
    {"type": "chart", "title": ..., "description": ...,
     "chart_data": {type:"bar", data:{labels, datasets:[Dividendo, JCP]}}}

  Tipo doughnut / Top-empresas bar / Calendário bar + table:
    the [v2] Proventos reorganization builders (BDR split + aggregation
    views) — see the individual docstrings.

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

[v2] Proventos reorganization (WebUI v1.18 family parity):
  - PT-BR accents everywhere ("Código", "Distribuição", "Próximo
    Pagamento" — the v1 static's strings were ASCII-fied, the fix the
    acoes skill got in v1.17).
  - The bucketing + the BDR predicate + the per-empresa/per-day
    aggregations moved to skills/ddm/dividends/helpers.py (the shared
    numerics module — ONE bucketing used by the static AND the WebUI
    DividendosService; report.py keeps only the presentation).
  - BDR split: B3 BDR tickers end in "34" (AAPL34, GDBR34...). Their
    payouts live in a different value universe (R$ 1,70-6,32 vs natives
    topping at ~R$ 1,13), so the agenda views split on is_bdr() — the
    Proventos tab keeps the B3 natives, the BDRs tab carries the rest.
"""

from __future__ import annotations

from skills._base.kpi import build_kpi_card
from skills._base.error import build_error_section
from skills.ddm.dividends.helpers import (
    DISTRIBUTION_BUCKETS,
    bucketize,
    format_brl,
    format_date,
    format_int,
    is_bdr,
)


# Distribution chart colors (mirrors the user spec):
#   Dividendo = teal #0d9488
#   JCP       = amber #f59e0b
_COLOR_DIVIDENDO = "#0d9488"
_COLOR_JCP = "#f59e0b"

# [v2] BDR accent color — slate, deliberately NEITHER teal nor amber (the
# tipo palette) so "é BDR" can never be misread as "é Dividendo/JCP".
_COLOR_BDR = "#94a3b8"


def build_dividends_table(title: str, dividends: list[dict],
                          description: str = "") -> dict:
    """Build a sortable agenda table.

    Columns: Código | Tipo | Valor (R$) | Registro | Ex | Pagamento

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
            tipo_cell = {"text": tipo_raw, "color": _COLOR_JCP}
        else:
            tipo_cell = {"text": tipo_raw, "color": _COLOR_DIVIDENDO}

        # [v2] BDR tickers get the slate accent (the visual BDR cue in
        # the mixed views; the scoped tabs are homogeneous anyway).
        ticker = d.get("ticker", "") or ""
        ticker_cell: dict | str = (
            {"text": ticker, "color": _COLOR_BDR} if is_bdr(ticker)
            else ticker
        )

        rows.append([
            ticker_cell,
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
            "Código", "Tipo", "Valor (R$)",
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
    """Build a grouped bar chart of event count per value range.

    2 datasets (side-by-side bars, NOT stacked):
      - Dividendo (teal #0d9488)
      - JCP       (amber #f59e0b)

    8 value-range buckets on the X-axis:
      <0,05 | 0,05-0,10 | 0,10-0,25 | 0,25-0,50 |
      0,50-1,00 | 1,00-2,00 | 2,00-5,00 | ≥5,00

    Y-axis: count of events in each bucket.

    [v2] The counting itself lives in helpers.bucketize (the shared
    numerics — the SAME function the WebUI DividendosService uses; this
    builder is presentation only).

    Args:
        title:       Chart title.
        dividends:   List of {ticker, tipo, value, ...} dicts.
        description: Optional description.
    """
    b = bucketize(dividends)
    return {
        "type":        "chart",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": b["labels"],
                "datasets": [
                    {
                        "type":            "bar",
                        "label":           "Dividendo",
                        "data":            b["dividendo"],
                        "backgroundColor": _COLOR_DIVIDENDO,
                        "borderColor":     _COLOR_DIVIDENDO,
                        "borderWidth":     0,
                    },
                    {
                        "type":            "bar",
                        "label":           "JCP",
                        "data":            b["jcp"],
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
                    "y": {"title": {"display": True, "text": "Quantidade de proventos"},
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


def build_tipo_doughnut(title: str, dividends: list[dict],
                        description: str = "") -> dict:
    """[v2] Build a doughnut of the event count split Dividendo vs JCP.

    The doughnut is the "at a glance" tipo read the v1 static didn't
    have (its only tipo cue was the grouped bars). 2 slices, teal/amber
    (the established tipo palette), counts in the tooltips.
    """
    n_div = sum(1 for d in dividends
                if (d.get("tipo") or "").strip().upper() != "JCP")
    n_jcp = len(dividends) - n_div
    return {
        "type":        "chart",
        "chart_type":  "doughnut",
        "title":       title,
        "description": description,
        "chart_data": {
            "type": "doughnut",
            "data": {
                "labels": ["Dividendo", "JCP"],
                "datasets": [{
                    "label": "Proventos",
                    "data": [n_div, n_jcp],
                    "backgroundColor": [_COLOR_DIVIDENDO, _COLOR_JCP],
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "cutout": "45%",
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                    "tooltip": {"enabled": True},
                },
            },
        },
    }


def build_top_empresas_chart(title: str, empresas: list[dict],
                             metric: str = "value",
                             description: str = "") -> dict:
    """[v2] Build a horizontal-ish bar of the top 10 empresas.

    metric="value"  -> bars of the summed per-share value (R$).
    metric="events" -> bars of the event count.

    Two datasets by BDR class — "B3" (teal) and "BDR" (slate) — so the
    chart SHOWS the split the agenda carries (the top of the value
    ranking is BDR-dominated; that's the insight). A ticker belongs to
    exactly one dataset, so the bars never collide.
    """
    top = empresas[:10]
    if not top:
        return build_error_section(title, "sem empresas para exibir")
    by_metric = (lambda e: e.get("total_value") or 0.0) if metric == "value" \
        else (lambda e: e.get("events") or 0)
    top = sorted(top, key=by_metric, reverse=True)
    labels = [e["ticker"] for e in top]
    # One array per dataset, aligned with `labels`: the value where the
    # ticker belongs to that class, None elsewhere (a ticker is in exactly
    # one class, so each label gets exactly one bar).
    b3 = [round(by_metric(e), 6) if not e["is_bdr"] else None for e in top]
    bdr = [round(by_metric(e), 6) if e["is_bdr"] else None for e in top]
    y_title = "Valor somado (R$)" if metric == "value" else "Nº de eventos"
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
                        "label":           "B3",
                        "data":            b3,
                        "backgroundColor": _COLOR_DIVIDENDO,
                        "borderColor":     _COLOR_DIVIDENDO,
                        "borderWidth":     0,
                    },
                    {
                        "type":            "bar",
                        "label":           "BDR",
                        "data":            bdr,
                        "backgroundColor": _COLOR_BDR,
                        "borderColor":     _COLOR_BDR,
                        "borderWidth":     0,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"title": {"display": True, "text": "Empresa"}},
                    "y": {"title": {"display": True, "text": y_title},
                          "beginAtZero": True},
                },
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


def build_empresa_table(title: str, empresas: list[dict],
                        description: str = "") -> dict:
    """[v2] Build the per-empresa aggregation table ("quem paga?").

    Columns: Empresa | Tipo | Eventos | Valor Total (R$) | Média (R$) |
    Máximo (R$) | Último Pagamento. The Tipo cell carries the Dividendo/
    JCP mix ("2 Div + 1 JCP"); BDR tickers get the slate accent + a BDR
    tooltip. Default sort: Valor Total DESC.
    """
    rows = []
    for e in empresas:
        ticker = e["ticker"]
        mix = []
        if e.get("n_dividendo"):
            mix.append(f"{e['n_dividendo']} Div")
        if e.get("n_jcp"):
            mix.append(f"{e['n_jcp']} JCP")
        ticker_cell: dict | str = ticker
        if e["is_bdr"]:
            ticker_cell = {
                "text": ticker, "color": _COLOR_BDR,
                "tooltip": "BDR — Brazilian Depositary Receipt "
                           "(empresa estrangeira negociada na B3).",
            }
        max_ev = e.get("max_event") or {}
        rows.append([
            ticker_cell,
            " + ".join(mix) or "—",
            format_int(e.get("events")),
            {"text": format_brl(e.get("total_value")),
             "data-value": f"{e.get('total_value') or 0:.6f}"},
            {"text": format_brl(e.get("avg_value")),
             "data-value": f"{e.get('avg_value') or 0:.6f}"},
            {"text": format_brl(max_ev.get("value")),
             "data-value": f"{max_ev.get('value') or 0:.6f}"},
            format_date(e.get("last_payment", "")),
        ])
    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      [
            "Empresa", "Tipo", "Eventos", "Valor Total (R$)",
            "Média (R$)", "Máximo (R$)", "Último Pagamento",
        ],
        "rows":         rows,
        "column_align": ["left", "left", "right", "right", "right",
                         "right", "right"],
        "sortable":     True,
        "sort_types":   ["text", "text", "number", "number", "number",
                         "number", "text"],
        "default_sort": {"column": 3, "direction": "desc"},
    }


def build_calendario_chart(title: str, days: list[dict],
                           today_iso: str = "",
                           description: str = "") -> dict:
    """[v2] Build the per-day payments bar chart ("quando cai?").

    One bar per payment date (value in R$), colored by status vs
    `today_iso`: already PAID (teal) vs still TO PAY (amber) — the
    calendar's forward-looking read.
    """
    # Labels are dd/mm ("03/11") — the static's 17-30 bars; the WebUI
    # twin ships ISO labels for its date-axis formatter.
    labels = [format_date(d["date"])[:5] for d in days]
    paid = [round(d["value"], 6) if d["date"] < today_iso else None
            for d in days]
    topay = [round(d["value"], 6) if d["date"] >= today_iso else None
             for d in days]
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
                        "label":           "Pago",
                        "data":            paid,
                        "backgroundColor": _COLOR_DIVIDENDO,
                        "borderColor":     _COLOR_DIVIDENDO,
                        "borderWidth":     0,
                    },
                    {
                        "type":            "bar",
                        "label":           "A pagar",
                        "data":            topay,
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
                    "x": {"title": {"display": True,
                                    "text": "Data de pagamento"}},
                    "y": {"title": {"display": True, "text": "Valor (R$)"},
                          "beginAtZero": True},
                },
                "plugins": {
                    "title":  {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


def build_calendario_table(title: str, days: list[dict],
                           description: str = "") -> dict:
    """[v2] Build the per-day payments table.

    Columns: Data | Eventos | BDRs | Valor Total (R$) | Valor BDR (R$) |
    Principais Pagadores. The Data cell's tooltip carries the day's
    top-3 payers; "Principais Pagadores" is the readable inline form.
    """
    rows = []
    for d in days:
        payers = " · ".join(f"{t} ({format_brl(v)})" for t, v in d["payers"])
        tip = " · ".join(f"{t}: {format_brl(v)}" for t, v in d["payers"])
        rows.append([
            {"text": format_date(d["date"]),
             "tooltip": f"Maiores pagadores do dia: {tip}." if tip else ""},
            format_int(d["events"]),
            format_int(d["bdr_events"]),
            {"text": format_brl(d["value"]),
             "data-value": f"{d['value']:.6f}"},
            {"text": format_brl(d["bdr_value"]),
             "data-value": f"{d['bdr_value']:.6f}"},
            payers or "—",
        ])
    return {
        "type":         "table",
        "title":        title,
        "description":  description,
        "columns":      [
            "Data", "Eventos", "BDRs", "Valor Total (R$)",
            "Valor BDR (R$)", "Principais Pagadores",
        ],
        "rows":         rows,
        "column_align": ["left", "right", "right", "right", "right", "left"],
        "sortable":     True,
        "sort_types":   ["text", "number", "number", "number", "number",
                         "text"],
        "default_sort": {"column": 0, "direction": "desc"},
    }


# Helper: expose format_int so the dashboard mode can format count KPIs.
def _format_count(v) -> str:
    """Format an integer count using PT-BR thousands separators."""
    return format_int(v)


# Backwards-compatible alias: the v1 module carried the buckets locally;
# helpers.DISTRIBUTION_BUCKETS is the single source now.
_DISTRIBUTION_BUCKETS = DISTRIBUTION_BUCKETS
