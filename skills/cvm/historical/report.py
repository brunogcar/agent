"""skills/cvm/historical/report.py -- Dashboard composition helpers.

[v1.15] Tooltips, chart titles, trend line charts, 5Y averages, split tables.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from tools.report_ops.formats import apply_fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_shared_tooltip
from skills.cvm.calculations._registry import resolve_metric
from skills.cvm.historical.helpers import _months_ago

def _fmt(v, s):
    if v is None: return "—"
    try: return apply_fmt(v, s)
    except Exception: return str(v)

def _num(v):
    if v is None: return None
    if isinstance(v, (int, float)): return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except: return v

def _kpi(l, v, s, u):
    return {"label": l, "value": _fmt(v, s) if v is not None else "—", "unit": u}

def _ok(d): return isinstance(d, dict) and d.get("status") == "ok"

def _cell(label, tooltip=""):
    return {"text": label, "tooltip": tooltip} if tooltip else label

def _tip(m): return _get_shared_tooltip(m)

def _scaled(v, s):
    return round(v * s, 4) if v is not None else None

def _change(c, a):
    if c is None or a is None or a == 0: return None
    return round((c - a) / a, 4)

def compute_quartiles(series, ratio_key):
    if not series: return None
    vals = sorted(s[ratio_key] for s in series if s.get(ratio_key) is not None and s[ratio_key] > 0)
    if not vals: return None
    n = len(vals)
    def _pct(p): return vals[min(int(round(p/100*(n-1))), n-1)]
    return {"min": vals[0], "p25": _pct(25), "median": _pct(50), "p75": _pct(75), "max": vals[-1], "count": n}

def fetch_quartiles(company, metric_name, months=60):
    try:
        spec = resolve_metric(metric_name)
        series = spec.history_fn(company, _months_ago(max(months, 60)), datetime.now().strftime("%Y-%m-%d"))
        return compute_quartiles(series, spec.ratio_key)
    except: return None

def fetch_series(company, metric_name, months=60):
    try:
        spec = resolve_metric(metric_name)
        return spec.history_fn(company, _months_ago(max(months, 60)), datetime.now().strftime("%Y-%m-%d"))
    except: return None

def build_overview_kpis(summaries, metric_defs):
    kpis = []
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}
        if not _ok(s): kpis.append(_kpi(label, None, "num", unit)); continue
        try: spec = resolve_metric(mn)
        except: kpis.append(_kpi(label, None, "num", unit)); continue
        v = s.get("current", {}).get(spec.ratio_key)
        kpis.append(_kpi(label, v, "pct" if unit == "pct" else "num", unit))
    return kpis

def build_overview_section(summaries, metric_defs, company):
    lines = [f"Empresa: {company}", "Métricas:"]
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}
        if not _ok(s): lines.append(f"  - {label}: indisponível"); continue
        try: spec = resolve_metric(mn)
        except: lines.append(f"  - {label}: indisponível"); continue
        v = s.get("current", {}).get(spec.ratio_key)
        lines.append(f"  - {label}: {_fmt(v, 'pct' if unit=='pct' else 'num')}")
    return {"title": "Resumo", "type": "text", "text": "\n".join(lines)}

def build_percentile_section(summaries, quartiles, metric_defs):
    cols = ["Métrica", "Atual", "Min", "25º", "Mediana", "75º", "Max", "Percentil", "Interpretação"]
    fmts = {c: "num" for c in cols[1:-1]}
    fmts["Métrica"] = "text"; fmts["Interpretação"] = "text"
    rows = []
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}; q = quartiles.get(mn) or {}
        if not _ok(s): rows.append([_cell(label, _tip(mn))] + ["—" for _ in cols[1:]]); continue
        try: spec = resolve_metric(mn)
        except: rows.append([_cell(label, _tip(mn))] + ["—" for _ in cols[1:]]); continue
        cur = s.get("current", {}).get(spec.ratio_key)
        sc = 100.0 if unit == "pct" else 1.0
        rows.append([_cell(label, _tip(mn)), _num(_scaled(cur, sc)), _num(_scaled(q.get("min"), sc)),
                     _num(_scaled(q.get("p25"), sc)), _num(_scaled(q.get("median"), sc)),
                     _num(_scaled(q.get("p75"), sc)), _num(_scaled(q.get("max"), sc)),
                     s.get("percentile"), s.get("interpretation", "—")])
    return {"title": "Análise de Percentis (5A)", "description": "Onde o valor atual está vs distribuição histórica.",
            "type": "table", "columns": cols, "rows": rows, "formats": fmts}

def build_trend_section(summaries, metric_defs):
    cols = ["Métrica", "Atual", "1A Média", "1A Var.", "3A Média", "3A Var.", "5A Média", "5A Var."]
    fmts = {"Métrica": "text", "Atual": "num", "1A Média": "num", "1A Var.": "pct",
            "3A Média": "num", "3A Var.": "pct", "5A Média": "num", "5A Var.": "pct"}
    rows = []
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}
        if not _ok(s): rows.append([_cell(label, _tip(mn))] + ["—" for _ in cols[1:]]); continue
        try: spec = resolve_metric(mn)
        except: rows.append([_cell(label, _tip(mn))] + ["—" for _ in cols[1:]]); continue
        cur = s.get("current", {}).get(spec.ratio_key)
        avgs = s.get("averages", {})
        sc = 100.0 if unit == "pct" else 1.0
        rows.append([_cell(label, _tip(mn)), _num(_scaled(cur, sc)),
                     _num(_scaled(avgs.get("1y"), sc)), _num(_change(cur, avgs.get("1y"))),
                     _num(_scaled(avgs.get("3y"), sc)), _num(_change(cur, avgs.get("3y"))),
                     _num(_scaled(avgs.get("5y"), sc)), _num(_change(cur, avgs.get("5y")))])
    return {"title": "Tendência (Atual vs 1A/3A/5A)", "description": "Var. = (atual - média) / média.",
            "type": "table", "columns": cols, "rows": rows, "formats": fmts}

def build_trend_line_chart(series, label, ratio_key):
    if not series or len(series) < 2: return None
    filtered = [(s.get("date",""), s.get(ratio_key)) for s in series if s.get(ratio_key) is not None]
    if len(filtered) < 2: return None
    dates, values = zip(*filtered)
    return {"type": "chart", "title": f"{label} — Série 5A", "description": f"Evolução de {label}.",
            "chart_data": {"type": "line", "data": {"labels": list(dates),
                "datasets": [{"label": label, "data": list(values), "borderColor": "#0d9488",
                    "fill": False, "tension": 0.3, "pointRadius": 0}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                    "scales": {"x": {"ticks": {"maxTicksLimit": 12}}},
                    "plugins": {"title": {"display": True, "text": f"{label} — 5A"}}}}}

def build_percentile_chart(summaries, quartiles, metric_defs):
    labels, cur_vals, med_vals = [], [], []
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}; q = quartiles.get(mn) or {}
        if not _ok(s): continue
        try: spec = resolve_metric(mn)
        except: continue
        cur = s.get("current", {}).get(spec.ratio_key); med = q.get("median")
        if cur is None and med is None: continue
        sc = 100.0 if unit == "pct" else 1.0
        labels.append(label); cur_vals.append(_scaled(cur, sc)); med_vals.append(_scaled(med, sc))
    if not labels: return None
    return {"type": "chart", "title": "Atual vs Mediana 5A", "description": "Comparativo.",
            "chart_data": {"type": "bar", "data": {"labels": labels,
                "datasets": [{"label": "Atual", "data": cur_vals, "backgroundColor": "#0d9488"},
                             {"label": "Mediana 5A", "data": med_vals, "backgroundColor": "#f59e0b"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                    "scales": {"y": {"ticks": {}}},
                    "plugins": {"title": {"display": True, "text": "Atual vs Mediana 5A"}}}}}

_GRID_CATS = {"ratio": "Valuation", "pct": "Rentabilidade"}

def build_ratio_grid_section(summaries, metric_defs):
    """Build split tables with columns: Métrica, Atual, 1A, 3A, 5A."""
    sections = []
    cats = {}
    for mn, label, unit in metric_defs:
        s = summaries.get(mn) or {}
        if not _ok(s): continue
        try: spec = resolve_metric(mn)
        except: continue
        cur = s.get("current", {}).get(spec.ratio_key)
        avgs = s.get("averages", {})
        sc = 100.0 if unit == "pct" else 1.0
        ss = "pct" if unit == "pct" else "num"
        cl = _GRID_CATS.get(unit, unit.capitalize())
        cats.setdefault(cl, []).append([_cell(label, _tip(mn)),
            _fmt(_scaled(cur, sc), ss), _fmt(_scaled(avgs.get("1y"), sc), ss),
            _fmt(_scaled(avgs.get("3y"), sc), ss), _fmt(_scaled(avgs.get("5y"), sc), ss)])
    for cl, rows in cats.items():
        sections.append({"title": f"{cl} — Atual vs Médias", "description": "Comparação com 1, 3 e 5 anos.",
                         "type": "table", "columns": ["Métrica", "Atual", "1A", "3A", "5A"], "rows": rows})
    return sections if sections else [{"type": "text", "text": "Sem dados."}]
