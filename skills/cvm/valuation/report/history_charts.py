"""report/history_charts.py — 5Y historical evolution step-line charts.

Contains:
  - build_pl_lpa_pvp_vpa_history_chart — P/L, LPA, P/VP, VPA daily evolution
    (merges lpa_history() + vpa_history() into a 4-dataset step-line chart)
  - build_roe_trend_chart              — ROIC / ROE / ROA 5Y quarterly
    step-line evolution with forward-fill (merges roe_history +
    roa_history + roic_history)

Both use the calculations registry's *_history() functions which return
step-function data (fundamentals change quarterly, price changes daily).
The step-line visual style (tension:0, stepped:'after') matches the
reference design: staircase lines holding constant between reporting dates.
"""
from __future__ import annotations


# ── V6: Historical evolution charts (step-line, 5Y) ──────────────────────────

def build_pl_lpa_pvp_vpa_history_chart(company: str) -> dict | None:
    """Build the P/L + LPA + P/VP + VPA 5Y historical evolution chart.

    Merges lpa_history() and vpa_history() (both daily, keyed by date) into
    a single step-line chart with 4 datasets. LPA/VPA are per-share BRL
    values (step-like — change quarterly). P/L and P/VP are price ratios
    (vary daily with price).

    All 4 share a single Y-axis (matching the reference design) so the
    viewer can compare their relative evolution over time. The description
    notes the scale difference.

    Returns a chart section dict, or None if no history data is available.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.lpa import lpa_history
        from skills.cvm.calculations.metrics.vpa import vpa_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        lpa_series = lpa_history(company, date_from, date_to)
        vpa_series = vpa_history(company, date_from, date_to)
    except Exception:
        return None

    if not lpa_series and not vpa_series:
        return None

    # Merge by date. Both series are daily (from price_series), so dates
    # should largely overlap. Build a unified dict {date: {pe, lpa, pvpa, vpa}}.
    merged: dict[str, dict] = {}
    for pt in lpa_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {
                "pe":  pt.get("pe"),
                "lpa": pt.get("lpa"),
            }
    for pt in vpa_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["pvpa"] = pt.get("pvpa")
        merged[d]["vpa"]  = pt.get("vpa")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    labels: list[str] = []
    pe_vals: list[float | None] = []
    lpa_vals: list[float | None] = []
    pvpa_vals: list[float | None] = []
    vpa_vals: list[float | None] = []

    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        pe_vals.append(entry.get("pe"))
        lpa_vals.append(entry.get("lpa"))
        pvpa_vals.append(entry.get("pvpa"))
        vpa_vals.append(entry.get("vpa"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "P/L",
                    "data": pe_vals,
                    "borderColor": "#1e40af",   # dark blue
                    "backgroundColor": "rgba(30,64,175,0.1)",
                    "tension": 0,
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "LPA",
                    "data": lpa_vals,
                    "borderColor": "#60a5fa",   # light blue
                    "backgroundColor": "rgba(96,165,250,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "P/VP",
                    "data": pvpa_vals,
                    "borderColor": "#dc2626",   # red
                    "backgroundColor": "rgba(220,38,38,0.1)",
                    "tension": 0,
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "VPA",
                    "data": vpa_vals,
                    "borderColor": "#f9a8d4",   # pink/salmon
                    "backgroundColor": "rgba(249,168,212,0.1)",
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
                    "title": {"display": True, "text": "Valor (R$ / múltiplo)"},
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
        "title": f"P/L, LPA, P/VP, VPA — Evolução 5A — {company}",
        "description": (
            "Evolução histórica de P/L (azul), LPA (azul claro), P/VP "
            "(vermelho) e VPA (rosa). LPA/VPA mudam trimestralmente (escada); "
            "P/L e P/VP variam diariamente com o preço. Eixo único — "
            "comparar a evolução relativa, não o valor absoluto."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": pe_vals},
            {"data": lpa_vals},
            {"data": pvpa_vals},
            {"data": vpa_vals},
        ],
        "price_full_data": pe_vals,
    }


def build_roe_trend_chart(company: str) -> dict | None:
    """Build the ROE/ROA/ROIC 5Y historical step-line chart.

    Uses roe_history(), roa_history(), roic_history() from the calculations
    registry. These return quarterly step-function data (fundamentals change
    only when new ITR/DFP filings arrive). The chart uses stepped:'after'
    styling to produce the staircase visual matching the reference design.

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.roe import roe_history
        from skills.cvm.calculations.metrics.roa import roa_history
        from skills.cvm.calculations.metrics.roic import roic_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        roe_series = roe_history(company, date_from, date_to)
        roa_series = roa_history(company, date_from, date_to)
        roic_series = roic_history(company, date_from, date_to)
    except Exception:
        return None

    if not roe_series and not roa_series and not roic_series:
        return None

    # Build per-metric {date: value} dicts, then merge into a unified
    # date axis with forward-fill (carry forward last known value).
    roe_map: dict[str, float | None] = {}
    roa_map: dict[str, float | None] = {}
    roic_map: dict[str, float | None] = {}

    for pt in roe_series:
        d = pt.get("date", "")
        if d:
            roe_map[d] = pt.get("roe")
    for pt in roa_series:
        d = pt.get("date", "")
        if d:
            roa_map[d] = pt.get("roa")
    for pt in roic_series:
        d = pt.get("date", "")
        if d:
            roic_map[d] = pt.get("roic")

    all_dates = sorted(set(roe_map) | set(roa_map) | set(roic_map))
    if len(all_dates) < 2:
        return None

    # Forward-fill: for each date, carry forward the last known value.
    labels: list[str] = []
    roe_vals: list[float | None] = []
    roa_vals: list[float | None] = []
    roic_vals: list[float | None] = []

    _last_roe: float | None = None
    _last_roa: float | None = None
    _last_roic: float | None = None

    for d in all_dates:
        labels.append(d)
        v = roe_map.get(d)
        _last_roe = v if v is not None else _last_roe
        roe_vals.append(_last_roe * 100 if _last_roe is not None else None)

        v = roa_map.get(d)
        _last_roa = v if v is not None else _last_roa
        roa_vals.append(_last_roa * 100 if _last_roa is not None else None)

        v = roic_map.get(d)
        _last_roic = v if v is not None else _last_roic
        roic_vals.append(_last_roic * 100 if _last_roic is not None else None)

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "ROIC %",
                    "data": roic_vals,
                    "borderColor": "#166534",   # dark green
                    "backgroundColor": "rgba(22,101,52,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "ROE %",
                    "data": roe_vals,
                    "borderColor": "#65a30d",   # olive/khaki green
                    "backgroundColor": "rgba(101,163,13,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "ROA %",
                    "data": roa_vals,
                    "borderColor": "#22c55e",   # bright green
                    "backgroundColor": "rgba(34,197,94,0.1)",
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
        "title": f"ROIC / ROE / ROA — Evolução 5A — {company}",
        "description": (
            "Evolução histórica dos retornos (escada trimestral). ROIC = "
            "retorno sobre capital investido; ROE = rentabilidade do capital "
            "dos acionistas; ROA = eficiência do uso dos ativos."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": roic_vals},
            {"data": roe_vals},
            {"data": roa_vals},
        ],
        "price_full_data": roe_vals,
    }
