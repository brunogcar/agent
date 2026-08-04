"""Mode: dashboard -- multi-tab historical dashboard with sidebar groups.

[v1.15] 5 tabs in 3 groups: Resumo / Avaliação / Análise.
"""
from __future__ import annotations
from skills._base import engine_cache_scope
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.historical._registry import register_mode
from skills.cvm.historical.modes.summary import summary
from skills.cvm.historical.report import (
    build_overview_kpis, build_overview_section, build_percentile_section,
    build_percentile_chart, build_trend_section, build_trend_line_chart,
    build_ratio_grid_section, fetch_quartiles, fetch_series, _fmt, _tip, _ok,
)
from skills.cvm.calculations._registry import resolve_metric

_METRIC_DEFS = [
    ("lpa", "P/L", "ratio", "valuation"), ("vpa", "P/VPA", "ratio", "valuation"),
    ("ev_ebitda", "EV/EBITDA", "ratio", "valuation"),
    ("roe", "ROE", "pct", "profitability"), ("roic", "ROIC", "pct", "profitability"),
    ("dpa", "Div Yield", "pct", "profitability"),
    ("gross_margin", "Marg. Bruta", "pct", "profitability"),
    ("net_margin", "Marg. Líquida", "pct", "profitability"),
]
_METRIC_DEFS_3 = [(m, l, u) for m, l, u, _ in _METRIC_DEFS]

@register_mode("dashboard",
    description="Multi-tab historical dashboard with sidebar groups.",
    params={"company": "str. Required."}, include_in_all=False,
    examples=['skill(domain="cvm", sub_domain="historical", mode="dashboard", params=\'{"company":"PETR4"}\')'],
)
def dashboard(company: str = "") -> dict:
    if not company:
        return {"status": "error", "error": "company is required"}
    print(f"[historical] Starting for {company}...", flush=True)

    summaries, quartiles, series_data = {}, {}, {}
    total = len(_METRIC_DEFS)
    print(f"[historical] Fetching {total} summaries (F7 cache)...", flush=True)
    with engine_cache_scope() as cache:
        for i, (mn, label, _, _) in enumerate(_METRIC_DEFS, 1):
            print(f"[historical]   {i}/{total}: {label}...", flush=True, end="")
            try: summaries[mn] = summary(company=company, metric=mn)
            except Exception as e: summaries[mn] = {"status": "error", "error": str(e)}
            print(" done.", flush=True)
        print(f"[historical] Fetching quartiles + series...", flush=True)
        for mn, _, _, _ in _METRIC_DEFS:
            s = summaries.get(mn) or {}
            if s.get("status") != "ok":
                quartiles[mn] = None; series_data[mn] = None; continue
            quartiles[mn] = fetch_quartiles(company, mn, 60)
            series_data[mn] = fetch_series(company, mn, 60)
        stats = cache.stats
        print(f"[historical] F7: {stats['hits']} hits, {stats['misses']} misses.", flush=True)

    print(f"[historical] Building header + price chart...", flush=True)
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

    print(f"[historical] Building sections...", flush=True)
    kpis = build_overview_kpis(summaries, _METRIC_DEFS_3)

    # Overview: header + price chart + split tables (Valuation + Rentabilidade)
    print(f"[historical]   Overview...", flush=True)
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info", "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    val_rows, prof_rows = [], []
    for mn, label, unit, _cat in _METRIC_DEFS:
        s = summaries.get(mn) or {}
        if not _ok(s): continue
        try: spec = resolve_metric(mn)
        except: continue
        cur = s.get("current", {}).get(spec.ratio_key)
        ss = "pct" if unit == "pct" else "num"
        row = [{"text": label, "tooltip": _tip(mn)}, _fmt(cur, ss)]
        if unit == "ratio": val_rows.append(row)
        else: prof_rows.append(row)
    if val_rows:
        overview_sections.append({"title": "Valuation", "type": "table", "columns": ["Métrica", "Valor"], "rows": val_rows})
    if prof_rows:
        overview_sections.append({"title": "Rentabilidade", "type": "table", "columns": ["Métrica", "Valor"], "rows": prof_rows})

    # Valuation + Profitability subtabs
    print(f"[historical]   Valuation...", flush=True)
    val_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "valuation"]
    val_s = {m: summaries.get(m, {}) for m, _, _ in val_metrics}
    val_q = {m: quartiles.get(m) for m, _, _ in val_metrics}
    val_subtabs = [
        {"name": "Percentil", "sections": [build_percentile_section(val_s, val_q, val_metrics)]},
        {"name": "Tendência", "sections": [build_trend_section(val_s, val_metrics)]},
    ]
    vc = build_percentile_chart(val_s, val_q, val_metrics)
    if vc: val_subtabs.insert(1, {"name": "Gráfico", "sections": [vc]})
    for mn, label, _ in val_metrics:
        try:
            spec = resolve_metric(mn)
            lc = build_trend_line_chart(series_data.get(mn), label, spec.ratio_key)
            if lc: val_subtabs.append({"name": f"{label} 5A", "sections": [lc]})
        except: pass
    valuation_sections = [{"type": "subtabs", "tabs": val_subtabs}]

    print(f"[historical]   Profitability...", flush=True)
    prof_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "profitability"]
    prof_s = {m: summaries.get(m, {}) for m, _, _ in prof_metrics}
    prof_q = {m: quartiles.get(m) for m, _, _ in prof_metrics}
    prof_subtabs = [
        {"name": "Percentil", "sections": [build_percentile_section(prof_s, prof_q, prof_metrics)]},
        {"name": "Tendência", "sections": [build_trend_section(prof_s, prof_metrics)]},
    ]
    pc = build_percentile_chart(prof_s, prof_q, prof_metrics)
    if pc: prof_subtabs.insert(1, {"name": "Gráfico", "sections": [pc]})
    for mn, label, _ in prof_metrics:
        try:
            spec = resolve_metric(mn)
            lc = build_trend_line_chart(series_data.get(mn), label, spec.ratio_key)
            if lc: prof_subtabs.append({"name": f"{label} 5A", "sections": [lc]})
        except: pass
    profitability_sections = [{"type": "subtabs", "tabs": prof_subtabs}]

    # Ratio Grid (now split tables)
    print(f"[historical]   Ratio Grid...", flush=True)
    grid_sections = build_ratio_grid_section(summaries, _METRIC_DEFS_3)

    # Percentile Analysis
    print(f"[historical]   Percentile Analysis...", flush=True)
    pct_sections = [build_percentile_section(summaries, quartiles, _METRIC_DEFS_3)]
    fc = build_percentile_chart(summaries, quartiles, _METRIC_DEFS_3)
    if fc: pct_sections.append(fc)

    # Freshness footer
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness(); last = get_last_synced_period()
        freshness_footer = (f"DFP: {fresh.get('dfp','')[:10] or '—'} (até {last.get('dfp','') or '—'}) • "
                            f"ITR: {fresh.get('itr','')[:10] or '—'} (até {last.get('itr','') or '—'}) • "
                            f"COTAHIST: {fresh.get('cotahist','')[:10] or '—'}")
    except: pass

    tabs = [
        {"name": "Overview", "group": "Resumo", "sections": overview_sections},
        {"name": "Valuation", "group": "Avaliação", "sections": valuation_sections},
        {"name": "Profitability", "group": "Avaliação", "sections": profitability_sections},
        {"name": "Ratio Grid", "group": "Análise", "sections": grid_sections},
        {"name": "Percentile Analysis", "group": "Análise", "sections": pct_sections},
    ]
    print(f"[historical] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)
    return {"status": "ok", "company": company, "company_header": company_header,
            "tabs": tabs, "kpis": kpis, "freshness_footer": freshness_footer}
