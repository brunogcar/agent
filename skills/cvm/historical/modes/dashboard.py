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
    build_ratio_grid_section, fetch_quartiles, fetch_series,
    compute_quartiles, _fmt, _tip, _ok,
)
from skills.cvm.calculations._registry import resolve_metric

_METRIC_DEFS = [
    ("lpa", "P/L", "ratio", "valuation"), ("vpa", "P/VPA", "ratio", "valuation"),
    ("ev_ebitda", "EV/EBITDA", "ratio", "valuation"),
    ("roe", "ROE", "pct", "profitability"), ("roic", "ROIC", "pct", "profitability"),
    ("dpa", "Div Yield", "pct", "profitability"),
    ("gross_margin", "Marg. Bruta", "pct", "profitability"),
    ("net_margin", "Marg. Líquida", "pct", "profitability"),
    # [v1.16] Leverage metrics
    ("debt_equity", "Dívida/PL", "ratio", "leverage"),
    ("net_debt_ebitda", "Dív. Líq./EBITDA", "ratio", "leverage"),
    ("interest_coverage", "Cobertura Juros", "ratio", "leverage"),
    # [v1.16] Efficiency metrics
    ("asset_turnover", "Giro Ativo", "ratio", "efficiency"),
    ("inventory_turnover", "Giro Estoque", "ratio", "efficiency"),
    # [v1.16] Growth metrics
    ("revenue_growth_3m", "Cresc. Receita", "pct", "growth"),
    ("net_income_growth_3m", "Cresc. Lucro", "pct", "growth"),
    # [v1.17] Market risk metrics (from BCB SGS + COTAHIST + brapi)
    ("coe", "COE (CAPM)", "pct", "market"),
    ("beta", "Beta (5A)", "ratio", "market"),
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
    print(f"[historical] Fetching {total} summaries (F7 cache, parallel)...", flush=True)
    # [v1.14] F7 cache scope wraps the WHOLE dashboard (main thread + workers).
    # Each worker ALSO enters its own engine_cache_scope() because Python's
    # ThreadPoolExecutor does NOT propagate ContextVar values to worker threads
    # — without the per-worker scope, @engine_cached becomes a passthrough in
    # all 17 parallel summaries (F7 hits=0 in workers).
    with engine_cache_scope() as cache:
        # [v1.17] Parallelize metric summary fetching (Mistral suggestion)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def _fetch_summary(mn):
            # [v1.14] Each worker gets its own F7 cache scope (ContextVar is
            # per-thread). This lets metrics sharing the same engine (e.g.,
            # earnings used by 5+ metrics) deduplicate within the worker.
            with engine_cache_scope():
                try:
                    return mn, summary(company=company, metric=mn)
                except Exception as e:
                    # [new commit] Include exception type name so signature-
                    # mismatch bugs (e.g. TypeError from beta_periods) are
                    # immediately visible in the dashboard output, not just
                    # the message string. Found by external LLM review (Claude 1).
                    return mn, {"status": "error",
                                "error": f"{type(e).__name__}: {e}"}

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_fetch_summary, mn): mn for mn, _, _, _ in _METRIC_DEFS}
            for future in as_completed(futures):
                mn, result = future.result()
                summaries[mn] = result
                print(f"[historical]   {mn}... done.", flush=True)

        print(f"[historical] Fetching quartiles + series (parallel)...", flush=True)
        # [v2 fix] PERF: fetch_series calls history_fn once; compute_quartiles
        # is done IN-MEMORY from the same series (was calling history_fn TWICE
        # — once in fetch_quartiles, once in fetch_series = 34 sequential calls).
        # Also parallelized like the summaries above.
        # IMPORTANT: uses the module-level fetch_series (NOT spec.history_fn
        # directly) so test mocks are respected. v1 called spec.history_fn
        # directly which bypassed the mock, making test_dashboard take minutes
        # (real DB calls for 17 metrics).
        def _fetch_series(mn):
            try:
                spec = resolve_metric(mn)
                s_data = fetch_series(company, mn, 60)
                q_data = compute_quartiles(s_data, spec.ratio_key,
                                            allow_negative=getattr(spec, "allow_negative", False))
                return mn, q_data, s_data
            except Exception:
                return mn, None, None

        with engine_cache_scope():
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_fetch_series, mn): mn for mn, _, _, _ in _METRIC_DEFS}
                for future in as_completed(futures):
                    mn, q, s = future.result()
                    # Only store if summary was ok (consistent with old behavior)
                    if (summaries.get(mn) or {}).get("status") == "ok":
                        quartiles[mn] = q
                        series_data[mn] = s
                    else:
                        quartiles[mn] = None
                        series_data[mn] = None
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

    # [v1.16] Leverage tab
    print(f"[historical]   Leverage...", flush=True)
    lev_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "leverage"]
    lev_s = {m: summaries.get(m, {}) for m, _, _ in lev_metrics}
    lev_q = {m: quartiles.get(m) for m, _, _ in lev_metrics}
    lev_subtabs = [
        {"name": "Percentil", "sections": [build_percentile_section(lev_s, lev_q, lev_metrics)]},
        {"name": "Tendência", "sections": [build_trend_section(lev_s, lev_metrics)]},
    ]
    lc_chart = build_percentile_chart(lev_s, lev_q, lev_metrics)
    if lc_chart: lev_subtabs.insert(1, {"name": "Gráfico", "sections": [lc_chart]})
    for mn, label, _ in lev_metrics:
        try:
            spec = resolve_metric(mn)
            lc = build_trend_line_chart(series_data.get(mn), label, spec.ratio_key)
            if lc: lev_subtabs.append({"name": f"{label} 5A", "sections": [lc]})
        except: pass
    leverage_sections = [{"type": "subtabs", "tabs": lev_subtabs}] if lev_metrics else []

    # [v1.16] Efficiency + Growth tab
    print(f"[historical]   Efficiency & Growth...", flush=True)
    eg_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c in ("efficiency", "growth")]
    eg_s = {m: summaries.get(m, {}) for m, _, _ in eg_metrics}
    eg_q = {m: quartiles.get(m) for m, _, _ in eg_metrics}
    eg_subtabs = [
        {"name": "Percentil", "sections": [build_percentile_section(eg_s, eg_q, eg_metrics)]},
        {"name": "Tendência", "sections": [build_trend_section(eg_s, eg_metrics)]},
    ]
    eg_chart = build_percentile_chart(eg_s, eg_q, eg_metrics)
    if eg_chart: eg_subtabs.insert(1, {"name": "Gráfico", "sections": [eg_chart]})
    for mn, label, _ in eg_metrics:
        try:
            spec = resolve_metric(mn)
            lc = build_trend_line_chart(series_data.get(mn), label, spec.ratio_key)
            if lc: eg_subtabs.append({"name": f"{label} 5A", "sections": [lc]})
        except: pass
    eg_sections = [{"type": "subtabs", "tabs": eg_subtabs}] if eg_metrics else []

    # [v1.17] Market risk tab (COE + Beta)
    print(f"[historical]   Market Risk...", flush=True)
    mkt_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "market"]
    mkt_s = {m: summaries.get(m, {}) for m, _, _ in mkt_metrics}
    mkt_q = {m: quartiles.get(m) for m, _, _ in mkt_metrics}
    mkt_subtabs = [
        {"name": "Percentil", "sections": [build_percentile_section(mkt_s, mkt_q, mkt_metrics)]},
        {"name": "Tendencia", "sections": [build_trend_section(mkt_s, mkt_metrics)]},
    ]
    mkt_chart = build_percentile_chart(mkt_s, mkt_q, mkt_metrics)
    if mkt_chart: mkt_subtabs.insert(1, {"name": "Grafico", "sections": [mkt_chart]})
    for mn, label, _ in mkt_metrics:
        try:
            spec = resolve_metric(mn)
            lc = build_trend_line_chart(series_data.get(mn), label, spec.ratio_key)
            if lc: mkt_subtabs.append({"name": f"{label} 5A", "sections": [lc]})
        except: pass
    mkt_sections = [{"type": "subtabs", "tabs": mkt_subtabs}] if mkt_metrics else []

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
    ]
    if leverage_sections:
        tabs.append({"name": "Liquidez e Alavancagem", "group": "Análise", "sections": leverage_sections})
    if eg_sections:
        tabs.append({"name": "Eficiencia e Crescimento", "group": "Analise", "sections": eg_sections})
    if mkt_sections:
        tabs.append({"name": "Risco de Mercado", "group": "Analise", "sections": mkt_sections})
    tabs.append({"name": "Ratio Grid", "group": "Analise", "sections": grid_sections})
    tabs.append({"name": "Percentile Analysis", "group": "Análise", "sections": pct_sections})

    print(f"[historical] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)
    return {"status": "ok", "company": company, "company_header": company_header,
            "tabs": tabs, "kpis": kpis, "freshness_footer": freshness_footer}
