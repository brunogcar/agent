"""report/profitability.py — Profitability tab + margins trend chart.

Contains:
  - build_profitability_section  — Retornos + Margens ratio_grids + bar charts
                                   with rich tooltip callbacks (formulas)
  - build_margin_trend_chart     — 5Y margins step-line chart (Gross / Operating
                                   / Net / EBITDA) from calculations registry
"""
from __future__ import annotations

import json

from skills.cvm.valuation.report._helpers import _safe_get, _fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── Tab 4: Profitability -- ratio_grid ───────────────────────────────────────

_PROFITABILITY_ITEMS: list[tuple[str, str, str]] = [
    ("ROE",            "roe",              "pct"),
    ("ROA",            "roa",              "pct"),
    ("ROIC",           "roic",             "pct"),
    ("Gross Margin",   "gross_margin",     "pct"),
    ("Operating Margin","operating_margin","pct"),
    ("Net Margin",     "net_margin",       "pct"),
    ("EBITDA Margin",  "ebitda_margin",    "pct"),
    ("OCF Margin",     "ocf_margin",       "pct"),
    ("FCF Margin",     "fcf_margin",       "pct"),
]


def build_profitability_section(ratios_dict: dict | None) -> list[dict]:
    """Build the Profitability tab — split ratio_grids + charts (Retornos + Margens).

    [v1.9] Split the single ratio_grid (2 categories) into TWO separate
    ratio_grids so the dashboard can group them under "Retornos" and
    "Margens" subtabs. Returns 4 sections in order:
      [0] Returns ratio_grid (1 category: Retornos, 3 items)
      [1] Returns chart (bar, with rich tooltips)
      [2] Margins ratio_grid (1 category: Margens, 6 items)
      [3] Margins chart (bar, with rich tooltips)

    Charts include explicit ``plugins.tooltip`` callbacks so each bar's
    tooltip shows the formula (PT-BR) alongside the value.
    """
    items = []
    for label, key, spec in _PROFITABILITY_ITEMS:
        raw = _safe_get(ratios_dict, key)
        items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
            "key": key,
        })
    returns_items = items[:3]
    margins_items = items[3:]

    sections: list[dict] = []

    # ── Returns ratio_grid ──
    sections.append({
        "title": "Retornos",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Retornos", "items": returns_items},
        ],
    })

    # ── Returns chart (ROE / ROA / ROIC) with rich tooltip ──
    ret_labels = [i["label"] for i in returns_items if i.get("value_raw") is not None]
    ret_values = [i["value_raw"] for i in returns_items if i.get("value_raw") is not None]
    ret_formulas = {i["label"]: i.get("tooltip", "") for i in returns_items}
    if len(ret_labels) >= 2:
        ret_pct = [v * 100 if abs(v) < 1 else v for v in ret_values]
        sections.append({
            "type": "chart",
            "title": "Retornos — ROE / ROA / ROIC",
            "description": "Comparativo dos retornos. Maior = melhor.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": ret_labels,
                         "datasets": [{"label": "Retornos (%)", "data": ret_pct,
                                       "backgroundColor": "#0d9488"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}},
                            "plugins": {
                                "tooltip": {
                                    "mode": "index",
                                    "intersect": False,
                                    "callbacks": {
                                        "afterLabel": (
                                            "function(ctx) {"
                                            f"  var m = {json.dumps(ret_formulas)};"
                                            "  return m[ctx.label] ? '\\n' + m[ctx.label] : '';"
                                            "}"
                                        ),
                                    },
                                },
                            }},
            },
        })

    # ── Margins ratio_grid ──
    sections.append({
        "title": "Margens",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Margens", "items": margins_items},
        ],
    })

    # ── Margins chart with rich tooltip ──
    mar_labels = [i["label"] for i in margins_items if i.get("value_raw") is not None]
    mar_values = [i["value_raw"] for i in margins_items if i.get("value_raw") is not None]
    mar_formulas = {i["label"]: i.get("tooltip", "") for i in margins_items}
    if len(mar_labels) >= 2:
        mar_pct = [v * 100 if abs(v) < 1 else v for v in mar_values]
        sections.append({
            "type": "chart",
            "title": "Margens — Bruta / EBIT / EBITDA / Líquida / FCO / FCF",
            "description": "Comparativo das margens operacionais. Maior = melhor.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": mar_labels,
                         "datasets": [{"label": "Margens (%)", "data": mar_pct,
                                       "backgroundColor": "#f59e0b"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}},
                            "plugins": {
                                "tooltip": {
                                    "mode": "index",
                                    "intersect": False,
                                    "callbacks": {
                                        "afterLabel": (
                                            "function(ctx) {"
                                            f"  var m = {json.dumps(mar_formulas)};"
                                            "  return m[ctx.label] ? '\\n' + m[ctx.label] : '';"
                                            "}"
                                        ),
                                    },
                                },
                            }},
            },
        })

    return sections


# ── V7: Margin trend 5Y step-line chart ──────────────────────────────────────

def build_margin_trend_chart(company: str) -> dict | None:
    """Build the Margins 5Y historical step-line chart.

    Uses gross_margin_history(), operating_margin_history(), net_margin_history(),
    ebitda_margin_history() from the calculations registry. These return
    quarterly step-function data (margins change when new ITR/DFP filings arrive).

    Plots 4 lines: Gross (blue), Operating (teal), Net (green), EBITDA (orange).
    Step-line style matching the ROE trend chart (stepped:'after', pointRadius:0).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.gross_margin import gross_margin_history
        from skills.cvm.calculations.metrics.operating_margin import operating_margin_history
        from skills.cvm.calculations.metrics.net_margin import net_margin_history
        from skills.cvm.calculations.metrics.ebitda_margin import ebitda_margin_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        gm_series = gross_margin_history(company, date_from, date_to)
        om_series = operating_margin_history(company, date_from, date_to)
        nm_series = net_margin_history(company, date_from, date_to)
        em_series = ebitda_margin_history(company, date_from, date_to)
    except Exception:
        return None

    if not gm_series and not om_series and not nm_series and not em_series:
        return None

    # Build per-metric {date: value} dicts
    gm_map: dict[str, float | None] = {}
    om_map: dict[str, float | None] = {}
    nm_map: dict[str, float | None] = {}
    em_map: dict[str, float | None] = {}

    for pt in gm_series:
        d = pt.get("date", "")
        if d:
            gm_map[d] = pt.get("gross_margin")
    for pt in om_series:
        d = pt.get("date", "")
        if d:
            om_map[d] = pt.get("operating_margin")
    for pt in nm_series:
        d = pt.get("date", "")
        if d:
            nm_map[d] = pt.get("net_margin")
    for pt in em_series:
        d = pt.get("date", "")
        if d:
            em_map[d] = pt.get("ebitda_margin")

    all_dates = sorted(set(gm_map) | set(om_map) | set(nm_map) | set(em_map))
    if len(all_dates) < 2:
        return None

    # Forward-fill
    labels: list[str] = []
    gm_vals: list[float | None] = []
    om_vals: list[float | None] = []
    nm_vals: list[float | None] = []
    em_vals: list[float | None] = []

    _last_gm = _last_om = _last_nm = _last_em = None

    for d in all_dates:
        labels.append(d)
        v = gm_map.get(d)
        _last_gm = v if v is not None else _last_gm
        gm_vals.append(_last_gm * 100 if _last_gm is not None else None)

        v = om_map.get(d)
        _last_om = v if v is not None else _last_om
        om_vals.append(_last_om * 100 if _last_om is not None else None)

        v = nm_map.get(d)
        _last_nm = v if v is not None else _last_nm
        nm_vals.append(_last_nm * 100 if _last_nm is not None else None)

        v = em_map.get(d)
        _last_em = v if v is not None else _last_em
        em_vals.append(_last_em * 100 if _last_em is not None else None)

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Margem Bruta",
                    "data": gm_vals,
                    "borderColor": "#3b82f6",   # blue
                    "backgroundColor": "rgba(59,130,246,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "Margem Operacional",
                    "data": om_vals,
                    "borderColor": "#0d9488",   # teal
                    "backgroundColor": "rgba(13,148,136,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "Margem Líquida",
                    "data": nm_vals,
                    "borderColor": "#22c55e",   # green
                    "backgroundColor": "rgba(34,197,94,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "Margem EBITDA",
                    "data": em_vals,
                    "borderColor": "#f59e0b",   # orange
                    "backgroundColor": "rgba(245,158,11,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "%"},
                },
                "x": {
                    "title": {"display": True, "text": "Data"},
                    "ticks": {"maxTicksLimit": 12},
                },
            },
            "plugins": {
                "legend": {"display": True, "position": "top"},
                "tooltip": {"mode": "index", "intersect": False},
            },
        },
    }

    return {
        "type": "chart",
        "title": f"Margens — Evolução 5A — {company}",
        "description": (
            "Evolução histórica das margens (escada trimestral). Bruta, "
            "Operacional, Líquida e EBITDA. Margens mudam quando novos "
            "resultados trimestrais são publicados."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": gm_vals},
            {"data": om_vals},
            {"data": nm_vals},
            {"data": em_vals},
        ],
        "price_full_data": nm_vals,
    }
