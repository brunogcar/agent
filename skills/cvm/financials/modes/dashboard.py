"""Mode: dashboard -- multi-tab financial dashboard (thin composition mode).

[v1.16] Critical bug fixes + new features:
  - 3T2025 skip bug fixed in fetchers._fetch_quarterly_cumulative
    (year filter + LIMIT scaled by empresa_id count).
  - Sidebar group rendering fixed in the financials_dashboard adapter
    (group field was being dropped).
  - DVA pie chart "Outros" bug fixed (new 7.08.* taxonomy + no parent/
    child double-count).
  - Crescimento 3M/1Y/5Y now computed (3M from quarterly QoQ; 6 annual
    periods fetched so 5Y has enough data).
  - Chart titles + descriptions added to every chart section.
  - Indicator tooltips (formula/explanation) on every ratio_grid item.
  - Indicadores Crescimento subtab split by metric (Receita/Lucro Líq./
    Resultado Bruto) instead of one "Outros" bucket.
  - Trimestral YoY table restructured to group by YEAR (primary) instead
    of by quarter.
  - New charts: Overview trend, Balanço structure, Anual multi-line,
    Trimestral bar.

11 tabs grouped into 4 sidebar sections:
  RESUMO:
    - Overview, Indicadores, Crescimento
  DEMONSTRAÇÕES:
    - Balanço, DRE, DFC, DVA
  PERÍODOS:
    - Anual, Trimestral
  SÉRIES TEMPORAIS:
    - Anualizado, Trimestral YoY
"""
from __future__ import annotations

from datetime import date

from skills._base import engine_cache_scope
from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.modes.annual import annual
from skills.cvm.financials.modes.quarterly import quarterly
from skills.cvm.financials.modes.ttm import ttm as ttm_mode
from skills.cvm.financials.modes.yoy_quarterly import yoy_quarterly as yoy_mode
from skills.cvm.financials.report import (
    annual_metric,
    annual_ratio,
    build_company_header,
    build_price_chart,
    build_overview_kpis,
    build_overview_sections,
    build_overview_trend_chart,
    build_indicadores_section,
    build_crescimento_sections,
    build_balanco_section,
    build_balanco_chart,
    build_balanco_decomp_charts,
    build_dre_sections,
    build_dfc_sections,
    build_dva_sections,
    # [new commit] F12/F13/F14 — new analytical sections.
    build_dfc_quality_section,
    build_dividend_sustainability_section,
    build_red_flags_section,
    build_dupont_section,
    build_altman_z_section,
    build_wacc_section,
    build_financials_radar,
    build_financials_heatmap,
    build_quality_of_earnings_section,  # [v2.4] F16
    build_quality_of_earnings_chart,    # [v2.4] F16
    build_error_section,
    build_ttm_chart,
    build_ttm_table,
    build_yoy_chart,
    build_yoy_table,
    build_period_table,
    build_period_chart,
    build_period_margins_chart,
    build_ttm_margins_chart,
    build_comprehensive_period_table,  # [v14] comprehensive period table
    build_indicator_charts,  # [v25] indicator bar charts
    # [v1.23 F4] New per-statement trend chart builders.
    build_statement_trend_chart,
    build_dfc_trend_chart,
    build_dva_trend_chart,
    build_multi_period_table,
)


def _safe_call(fn, *args, **kwargs):
    """Call a sub-mode and return its dict, or an error payload on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


@register_mode(
    "dashboard",
    description=(
        "Multi-tab financial dashboard. 11 tabs grouped into 4 sections: "
        "Resumo (Overview/Indicadores/Crescimento), Demonstrações "
        "(Balanço/DRE/DFC/DVA), Períodos (Anual/Trimestral), "
        "Séries Temporais (Anualizado/Trimestral YoY). "
        "KPI cards + charts + subtabs + ratio_grid."
    ),
    params={
        "company":     "str. Required.",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "", consolidado: int = 1) -> dict:
    """11-tab financial dashboard with sidebar grouping."""
    if not company:
        return {"status": "error", "error": "company is required"}

    from datetime import datetime as _dt
    _t0 = _dt.now()
    print(f"[financials] Starting dashboard for {company}...", flush=True)

    with engine_cache_scope() as cache:
        # [v1.22] Parallel fetch — annual, quarterly, statements, TTM, YoY
        # are all independent. Run them in parallel with ThreadPoolExecutor.
        # [v6 fix] Use contextvars.copy_context() to propagate the main thread's
        # engine cache to workers. Was each worker creating its own scope →
        # shared engines re-queried N times. Now all workers share the cache.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import contextvars

        today = date.today().isoformat()
        ratios_payload: dict = {"date": today}

        def _fetch_annual():
            return _safe_call(annual, company=company, periods=10, consolidado=consolidado)

        def _fetch_quarterly():
            return _safe_call(quarterly, company=company, periods=20, consolidado=consolidado)

        def _fetch_statements():
            return _fetch_all_statements(company, consolidado, period="annual")

        def _fetch_statements_q():
            return _fetch_all_statements(company, consolidado, period="quarterly")

        def _fetch_ttm():
            return _safe_call(ttm_mode, company=company, periods=20, consolidado=consolidado)

        def _fetch_yoy():
            return _safe_call(yoy_mode, company=company, years=5, consolidado=consolidado)

        def _fetch_ratios():
            try:
                from skills.cvm.calculations._registry import compute_all_ratios
                return compute_all_ratios(
                    company, today,
                    categories=["profitability", "liquidity", "leverage",
                                "efficiency", "growth", "tax", "valuation"],
                    exclude=["lpa", "vpa", "dpa", "rps"],
                )
            except Exception as e:
                return {"error": str(e)}

        def _fetch_capex():
            # [v2.4] Fetch real CapEx from the capex_at engine (description-
            # search: imobilizado/intangivel, scoped to DFC 6.02.%, TTM-
            # derived from DFP + ITR). Returns a {period_label: capex_value}
            # map keyed by date (YYYY-MM-DD) so the comprehensive table's
            # period labels can match.
            # [v2 fix] Only key by YEAR for DFP annual dates (month=12).
            # ITR dates (month=3/6/9) must NOT key by year — that collapses
            # all quarters of a year to one TTM value (the last ITR processed).
            # Quarterly periods match by their computed data_fim_exerc
            # (year+quarter → YYYY-MM-DD) in _extract_value's capex_engine
            # handler. Annual periods match by year (DFP Dec-31 → year key).
            # Engine calls share the engine_cache_scope cache with other tasks.
            try:
                from skills.cvm.calculations.engines.dfc.capex import capex_periods
                periods_list = capex_periods(company)
                capex_map: dict = {}
                for p in periods_list:
                    date = p.get("date") or ""
                    val = p.get("ttm_capex")
                    if date and val is not None:
                        # Always key by full date (e.g. "2026-06-30").
                        capex_map[date] = val
                        # Only key by year for DFP annual dates (month=12).
                        # ITR dates (month=3/6/9) are TTM at quarter-end —
                        # keying by year would overwrite with each quarter.
                        month = date[5:7] if len(date) >= 7 else ""
                        if month == "12":
                            year = date[:4]
                            if year:
                                capex_map[year] = val
                return capex_map
            except Exception as e:
                # [v2.5 fix] Log the exception so a structural failure (not
                # just "no data") is observable. The empty dict return
                # degrades gracefully (CAPEX falls back to FCI proxy) but
                # without this log the failure is completely silent.
                import sys
                print(f"[financials] CapEx engine fetch failed: {e}", file=sys.stderr, flush=True)
                return {}

        tasks = {
            "annual": _fetch_annual,
            "quarterly": _fetch_quarterly,
            "statements": _fetch_statements,
            "statements_q": _fetch_statements_q,
            "ttm": _fetch_ttm,
            "yoy": _fetch_yoy,
            "ratios": _fetch_ratios,
            "capex": _fetch_capex,  # [v2.4] real CapEx engine
        }

        results: dict[str, object] = {}
        # [v9 fix] Actually implement the copy_context propagation that the
        # comment above claimed was already done. Without this, worker threads
        # do NOT inherit the main thread's engine_cache_scope — every engine
        # call in TTM/quarterly/yoy runs uncached, causing 149s TTM times.
        #
        # A Context object can only be .run() in one thread at a time, so we
        # can't share one copy across all 6 workers. Instead, we pre-create
        # one copy per worker. All copies reference the SAME cache dict
        # (verified: same id()), so engine calls in one task hit the cache
        # populated by another task — true cross-task cache sharing.
        n_tasks = len(tasks)
        ctx_copies = [contextvars.copy_context() for _ in range(n_tasks)]

        def _run_with_ctx(ctx, fn):
            return ctx.run(fn)

        # [v1.24] max_workers bumped 6 → 7 for the new statements_q task.
        # [v2.4] max_workers bumped 7 → 8 for the new capex task.
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for i, (name, fn) in enumerate(tasks.items()):
                futures[executor.submit(_run_with_ctx, ctx_copies[i], fn)] = name
            for future in as_completed(futures):
                name = futures[future]
                _elapsed = (_dt.now() - _t0).total_seconds()
                try:
                    results[name] = future.result()
                    print(f"[financials]   {name} done ({_elapsed:.1f}s)", flush=True)
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
                    print(f"[financials]   {name} FAILED ({_elapsed:.1f}s): {e}", flush=True)

        annual_payload = results.get("annual", {})
        quarterly_payload = results.get("quarterly", {})
        bpa_result, bpp_result, dre_result, dfc_result, dva_result = results.get("statements", ({}, {}, {}, {}, {}))
        # [v1.24] Quarterly statement results (parallel-fetched alongside annual).
        # Each tuple element matches the annual tuple shape (5 statement results).
        bpa_result_q, bpp_result_q, dre_result_q, dfc_result_q, dva_result_q = (
            results.get("statements_q", ({}, {}, {}, {}, {})))
        ttm_result = results.get("ttm", {})
        yoy_result = results.get("yoy", {})
        ratios_payload.update(results.get("ratios", {}))
        # [v2.4] Real CapEx engine map — {date_or_year: capex_value}. Used by
        # build_comprehensive_period_table + build_indicator_charts for the
        # CAPEX row + the "EBIT, EBITDA e CAPEX" chart. Falls back to FCI
        # proxy when the engine returns None or the map is empty.
        capex_map: dict = results.get("capex", {}) or {}

        latest_annual_period: dict | None = None
        annual_periods: list[dict] = []
        if annual_payload.get("status") == "ok" and annual_payload.get("periods"):
            annual_periods = annual_payload["periods"]
            latest_annual_period = annual_periods[0]

        quarterly_periods: list[dict] = []
        if quarterly_payload.get("status") == "ok" and quarterly_payload.get("periods"):
            quarterly_periods = quarterly_payload["periods"]

        # [v2.2] TTM normalization block removed — TTM data now lives ONLY in
        # the standalone "Anualizado" tab (built below via build_ttm_table +
        # build_ttm_chart). The flow-statement builders (DRE/DFC/DVA) no
        # longer accept a ``ttm_periods`` kwarg.

        stats = cache.stats
        _fetch_elapsed = (_dt.now() - _t0).total_seconds()
        print(f"[financials] All data fetched in {_fetch_elapsed:.1f}s (cache: {stats['hits']} hits, {stats['misses']} misses)", flush=True)

    # ── Build sections ────────────────────────────────────────────────────
    # [v4] One-line section timers (ratios pattern): 11 sections.
    _SEC_TOTAL = 11
    _sec_count = 0
    _sec_t0 = _dt.now()

    # ── Section 1/11: Overview ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 1: Overview
    roe_val = ratios_payload.get("roe")
    if roe_val is None:
        roe_val = annual_ratio(latest_annual_period, "roe")
    roic_val = ratios_payload.get("roic")
    if roic_val is None:
        roic_val = annual_ratio(latest_annual_period, "roic")
    net_debt_ebitda_val = ratios_payload.get("net_debt_ebitda")

    kpis = build_overview_kpis(latest_annual_period, roe_val, roic_val,
                               net_debt_ebitda_val, ttm_result=ttm_result)
    # [v1.16.1] Company info card at the TOP of the Overview tab.
    # This pattern (company info + price chart at top of first tab) will be
    # reused by valuation/historical/governance dashboards — financials is
    # the template. The KPI boxes stay in the universal header (above tabs).
    # [v1.16.1] Build header ONCE and reuse — was called twice (P0 bug from
    # collective review). Second call was outside engine_cache_scope, causing
    # redundant FCA + CAD + COTAHIST queries.
    company_header = build_company_header(company)

    # [v24] Overview tab restructured into 4 subtabs:
    # 1. "Cotação & Resumo" — company info + price chart + summary text + quarterly trend
    # 2. "Trajetória Anual" — annual trend chart (Receita, EBITDA e Lucro)
    # 3. "Análise de Risco" — WACC + DuPont + Altman Z + Red Flags
    # 4. "Visão Multidimensional" — Radar + Heatmap
    overview_subtabs = []

    # Subtab 1: Cotação & Resumo
    sub1_sections = []
    if company_header.get("name"):
        sub1_sections.append({
            "type": "company_info",
            "company_header": company_header,
        })
    price_chart = build_price_chart(company)
    if price_chart:
        sub1_sections.append(price_chart)
    # Add summary text + quarterly trend from build_overview_sections
    base_overview = build_overview_sections(
        latest_annual_period, quarterly_periods, ratios_payload)
    sub1_sections.extend(base_overview)
    if sub1_sections:
        overview_subtabs.append({"name": "Cotação & Resumo", "sections": sub1_sections})

    # Subtab 2: Trajetória Anual
    sub2_sections = []
    overview_trend = build_overview_trend_chart(annual_periods, company)
    if overview_trend:
        sub2_sections.append(overview_trend)
    if sub2_sections:
        overview_subtabs.append({"name": "Trajetória Anual", "sections": sub2_sections})

    # Subtab 3: Análise de Risco
    # [v2.5 fix] WACC + Altman builders call wacc_history / altman_z_history
    # which make ~1,620 engine calls each (6 engines × 270 dates). These
    # MUST be wrapped in engine_cache_scope so the engine calls share the
    # cache populated by the parallel-fetch phase. Without this, every
    # engine call re-queries DFP/ITR/cotahist from scratch.
    sub3_sections = []
    try:
        with engine_cache_scope():
            wacc_sec = build_wacc_section(ratios_payload, company=company, today=today)
            if wacc_sec:
                sub3_sections.append(wacc_sec)
    except Exception as e:
        print(f"[financials] WACC section failed: {e}", flush=True)
    try:
        dupont_sec = build_dupont_section(ratios_payload)
        if dupont_sec:
            sub3_sections.append(dupont_sec)
    except Exception as e:
        print(f"[financials] DuPont section failed: {e}", flush=True)
    try:
        with engine_cache_scope():
            altman_sec = build_altman_z_section(ratios_payload, company=company, today=today)
            if altman_sec:
                sub3_sections.append(altman_sec)
    except Exception as e:
        print(f"[financials] Altman Z section failed: {e}", flush=True)
    try:
        red_flags = build_red_flags_section(
            bpa_result, bpp_result, dre_result, dfc_result, dva_result,
            annual_periods)
        if red_flags:
            sub3_sections.append(red_flags)
    except Exception as e:
        print(f"[financials] Red flags section failed: {e}", flush=True)
    # [v2.4] F16 — Quality of Earnings section + chart. Compares NI vs FCO
    # over the last 5 annual periods; flags red when accruals ratio > 30%
    # for 2+ consecutive years. Uses already-fetched annual_periods (no new
    # engine calls — the metrics come from the annual mode fetch).
    try:
        qoe_sec = build_quality_of_earnings_section(annual_periods, ratios_payload)
        if qoe_sec:
            sub3_sections.append(qoe_sec)
        qoe_chart = build_quality_of_earnings_chart(annual_periods)
        if qoe_chart:
            sub3_sections.append(qoe_chart)
    except Exception as e:
        print(f"[financials] Quality of Earnings section failed: {e}", flush=True)
    if sub3_sections:
        overview_subtabs.append({"name": "Análise de Risco", "sections": sub3_sections})

    # Subtab 4: Visão Multidimensional
    sub4_sections = []
    try:
        radar = build_financials_radar(ratios_payload)
        if radar:
            sub4_sections.append(radar)
    except Exception as e:
        print(f"[financials] Radar failed: {e}", flush=True)
    try:
        heatmap = build_financials_heatmap(ratios_payload)
        if heatmap:
            sub4_sections.append(heatmap)
    except Exception as e:
        print(f"[financials] Heatmap failed: {e}", flush=True)
    if sub4_sections:
        overview_subtabs.append({"name": "Visão Multidimensional", "sections": sub4_sections})

    # Wrap in subtabs if we have multiple, otherwise use flat list
    if len(overview_subtabs) > 1:
        overview_sections = [{"type": "subtabs", "tabs": overview_subtabs}]
    else:
        overview_sections = []
        for st in overview_subtabs:
            overview_sections.extend(st.get("sections", []))

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/11: Indicadores ─────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 2: Indicadores
    indicadores_section = build_indicadores_section(today, ratios_payload)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Indicadores ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/11: Crescimento ─────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 3: Crescimento
    # [new commit] Pass ratios_payload so growth values come from the
    # calculations registry (FIXED growth_at anchoring), consistent with
    # the historical dashboard. Eliminates F8 (sort bug) + F10 (duplication).
    crescimento_sections = build_crescimento_sections(
        latest_annual_period, annual_periods, quarterly_periods,
        ratios_payload=ratios_payload)

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Crescimento ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 4/11: Balanço ─────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 4: Balanço
    if bpa_result.get("status") == "ok" or bpp_result.get("status") == "ok":
        # [v1.25 v4] Build per-subtab charts for BOTH annual + quarterly
        # versions. The charts are passed into ``build_balanco_section`` which
        # puts them INSIDE the period_toggle (per subtab: Completo/BPA/BPP).
        # This replaces the old ``balanco_sections.extend(charts)`` pattern
        # where the 6 stacked-bar charts were top-level (outside the toggle)
        # and only switched when the user manually re-rendered.

        # Annual versions (no quarterly args → uses annual periods).
        # build_balanco_chart returns 2 charts (Completo abs + pct).
        completo_charts_annual = build_balanco_chart(bpa_result, bpp_result)
        # [v9] build_balanco_decomp_charts returns 8 charts: BPA [0:4] then
        # BPP [4:8]. Each group has 2 original stacked (abs+pct) + 2 single.
        decomp_annual = build_balanco_decomp_charts(bpa_result, bpp_result)
        bpa_charts_annual = decomp_annual[:4]
        bpp_charts_annual = decomp_annual[4:]

        # Quarterly versions (with quarterly args → uses quarterly periods).
        # Only built when both quarterly BPA + BPP are available.
        if bpa_result_q and bpp_result_q:
            completo_charts_quarterly = build_balanco_chart(
                bpa_result, bpp_result,
                bpa_result_q=bpa_result_q, bpp_result_q=bpp_result_q)
            decomp_quarterly = build_balanco_decomp_charts(
                bpa_result, bpp_result,
                bpa_result_q=bpa_result_q, bpp_result_q=bpp_result_q)
            bpa_charts_quarterly = decomp_quarterly[:4]
            bpp_charts_quarterly = decomp_quarterly[4:]
        else:
            completo_charts_quarterly = []
            bpa_charts_quarterly = []
            bpp_charts_quarterly = []

        # [v1.24] Pass quarterly BPA/BPP results so the period_toggle wraps
        # the multi-period table (annual + quarterly).
        # [v1.25 v4] Pass per-subtab annual + quarterly charts so they live
        # INSIDE the period_toggle (switch with Anual/Trimestral button).
        balanco_section = build_balanco_section(
            bpa_result, bpp_result,
            bpa_result_q=bpa_result_q, bpp_result_q=bpp_result_q,
            subtab_charts_annual={
                "Completo": completo_charts_annual,
                "BPA": bpa_charts_annual,
                "BPP": bpp_charts_annual,
            },
            subtab_charts_quarterly={
                "Completo": completo_charts_quarterly,
                "BPA": bpa_charts_quarterly,
                "BPP": bpp_charts_quarterly,
            },
        )
        # [v1.25 v4] The 6 stacked-bar charts are now INSIDE the toggle —
        # no longer appended as top-level sections.
        balanco_sections = [balanco_section]
    else:
        balanco_sections = [build_error_section("Balanço", "BPA/BPP indisponível")]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Balanço ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 5/11: DRE ─────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 5: DRE
    if dre_result.get("status") == "ok":
        # [v1.23 F4] Pass `company` so the DRE trend chart gets a price overlay.
        # [v1.24] Pass `dre_result_q` so the multi-period table is wrapped in
        # a period_toggle (annual + quarterly) and the trend chart uses
        # quarterly periods when available.
        # [v1.25 v4] Pass `quarterly_periods` so the margins + absolute-values
        # charts have quarterly versions inside the toggle.
        # [v2.2] TTM toggle reverted — no ttm_periods kwarg.
        dre_sections = build_dre_sections(
            dre_result, annual_periods, latest_annual_period,
            company=company, dre_result_q=dre_result_q,
            quarterly_periods=quarterly_periods)
    else:
        dre_sections = [build_error_section("DRE", dre_result.get("error", "unknown"))]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DRE ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 6/11: DFC ─────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 6: DFC
    if dfc_result.get("status") == "ok":
        # [v1.23 F4] Pass `company` so the DFC trend chart gets a price overlay.
        # [v1.24] Pass `dfc_result_q` for quarterly period_toggle + trend chart.
        # [v1.25 v4] Pass `quarterly_periods` so the stacked-bar + FCO-vs-LL
        # charts have quarterly versions inside the toggle.
        # [v2.2] TTM toggle reverted — no ttm_periods kwarg.
        dfc_sections = build_dfc_sections(
            dfc_result, annual_periods, latest_annual_period,
            company=company, dfc_result_q=dfc_result_q,
            quarterly_periods=quarterly_periods)
    else:
        dfc_sections = [build_error_section("DFC", dfc_result.get("error", "unknown"))]
    # [new commit] F12 — DFC quality analysis (appended after existing DFC
    # sections). Engine-backed (capex_at + operating_cf_at + ttm_earnings_at)
    # wrapped in its own engine_cache_scope so the 3 engine calls share one
    # cache (the dashboard's outer scope already exited at this point).
    try:
        with engine_cache_scope():
            dfc_quality = build_dfc_quality_section(
                latest_annual_period, company, today)
        if dfc_quality:
            dfc_sections.extend(dfc_quality)
    except Exception as e:
        print(f"[financials] DFC quality section failed: {e}", flush=True)

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DFC ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 7/11: DVA ─────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 7: DVA
    if dva_result.get("status") == "ok":
        # [v1.23 F4] Pass `company` so the DVA trend chart gets a price overlay.
        # [v1.24] Pass `dva_result_q` for quarterly period_toggle + trend chart.
        # [v2.2] TTM toggle reverted — no ttm_periods kwarg.
        dva_sections = build_dva_sections(
            dva_result, company=company, dva_result_q=dva_result_q)
    else:
        dva_sections = [build_error_section("DVA", dva_result.get("error", "unknown"))]
    # [new commit] F13 — Dividend sustainability (appended to DVA tab — DVA
    # is where dividends/distribution data lives). Engine-backed
    # (dividends_paid_at + dividends_paid_periods + ttm_earnings_at) wrapped
    # in engine_cache_scope for cache sharing across the 3 engine calls.
    try:
        with engine_cache_scope():
            div_sust = build_dividend_sustainability_section(
                ratios_payload, latest_annual_period, company, today)
        if div_sust:
            dva_sections.extend(div_sust)
    except Exception as e:
        print(f"[financials] Dividend sustainability section failed: {e}", flush=True)

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DVA ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 8/11: Anual ───────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # [v14] Tab 8: Anual — comprehensive table (Balanço+DRE+DFC+Indicadores)
    # + trend chart + margins chart. Replaces the simple 7-column table.
    if annual_payload.get("status") == "ok":
        try:
            # Build comprehensive table using annual_periods + statement results.
            # For annual, use the annual statement results (bpa_result etc.)
            # [v16] build_comprehensive_period_table now returns a LIST of 4 tables.
            anual_table = build_comprehensive_period_table(
                annual_periods, "Anual",
                bpa_result=bpa_result, bpp_result=bpp_result,
                dre_result=dre_result, dfc_result=dfc_result,
                capex_map=capex_map)
            anual_sections = list(anual_table)  # 4 section tables
            anual_chart = build_period_chart(annual_periods, "Anual")
            if anual_chart:
                anual_sections.append(anual_chart)
            # [v11] Add margins bar chart to the Anual tab
            anual_margins = build_period_margins_chart(annual_periods, "Anual")
            if anual_margins:
                anual_sections.append(anual_margins)
            # [v25] Add indicator charts (liquidez, endividamento, EBIT/EBITDA/CAPEX)
            try:
                ind_charts = build_indicator_charts(annual_periods, "Anual", bpa_result=bpa_result, bpp_result=bpp_result, capex_map=capex_map)
                anual_sections.extend(ind_charts)
            except Exception as e:
                print(f"[financials] Indicator charts failed: {e}", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            anual_sections = [build_error_section("Anual", str(e))]
    else:
        anual_sections = [build_error_section("Anual", annual_payload.get("error", "unknown"))]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Anual ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 9/11: Trimestral QoQ ───────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # [v15] Renamed from "Trimestral" to "Trimestral QoQ" per user request.
    # [v14] Comprehensive table + trend chart + margins.
    if quarterly_payload.get("status") == "ok":
        try:
            trimestral_table = build_comprehensive_period_table(
                quarterly_periods, "Trimestral QoQ",
                bpa_result=bpa_result_q, bpp_result=bpp_result_q,
                dre_result=dre_result_q, dfc_result=dfc_result_q,
                capex_map=capex_map)
            trimestral_sections = list(trimestral_table)  # 4 section tables
            trimestral_chart = build_period_chart(quarterly_periods, "Trimestral QoQ")
            if trimestral_chart:
                trimestral_sections.append(trimestral_chart)
            # [v11] Add margins bar chart to the Trimestral tab
            trimestral_margins = build_period_margins_chart(quarterly_periods, "Trimestral QoQ")
            if trimestral_margins:
                trimestral_sections.append(trimestral_margins)
            # [v25] Add indicator charts
            try:
                ind_charts = build_indicator_charts(quarterly_periods, "Trimestral QoQ", bpa_result=bpa_result_q, bpp_result=bpp_result_q, capex_map=capex_map)
                trimestral_sections.extend(ind_charts)
            except Exception as e:
                print(f"[financials] Indicator charts failed: {e}", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            trimestral_sections = [build_error_section("Trimestral QoQ", str(e))]
    else:
        trimestral_sections = [build_error_section("Trimestral QoQ", quarterly_payload.get("error", "unknown"))]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Trimestral ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 10/11: Anualizado (TTM) ───────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # [v14] Tab 10: TTM (Anualizado) — comprehensive table + chart + margins.
    # TTM periods don't have statement results, so accounts-based rows show "—".
    # The metrics-based rows (Receita, EBIT, EBITDA, Lucro, FCO, etc.) + ratios
    # will populate from the ttm_periods metrics/ratios dicts.
    ttm_sections: list[dict] = []
    if isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
        ttm_periods = ttm_result.get("periods") or []
        if ttm_periods:
            try:
                # [v19] Pass quarterly statement results for TTM — TTM period
                # labels (e.g. "2T2026") match quarterly statement result labels,
                # so accounts-based rows (Ativo Circ, Passivo, etc.) populate.
                # [v16] Returns a LIST of 4 tables.
                ttm_table = build_comprehensive_period_table(
                    ttm_periods, "Anualizado",
                    bpa_result=bpa_result_q, bpp_result=bpp_result_q,
                    dre_result=dre_result_q, dfc_result=dfc_result_q,
                    capex_map=capex_map)
                ttm_sections.extend(ttm_table)
                ttm_chart = build_ttm_chart(ttm_periods)
                if ttm_chart:
                    ttm_sections.append(ttm_chart)
                # [v11] Add margins bar chart to the Anualizado (TTM) tab
                ttm_margins = build_ttm_margins_chart(ttm_periods)
                if ttm_margins:
                    ttm_sections.append(ttm_margins)
                # [v25] Add indicator charts
                try:
                    ind_charts = build_indicator_charts(ttm_periods, "Anualizado", bpa_result=bpa_result_q, bpp_result=bpp_result_q, capex_map=capex_map)
                    ttm_sections.extend(ind_charts)
                except Exception as e:
                    print(f"[financials] TTM indicator charts failed: {e}", flush=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
                ttm_sections.append(build_error_section("Anualizado", str(e)))
    if not ttm_sections:
        ttm_sections = [build_error_section("Anualizado", ttm_result.get("error", "unknown") if isinstance(ttm_result, dict) else "unknown")]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Anualizado ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 11/11: Trimestral YoY ─────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # [v17] Trimestral YoY restructured — each quarter subtab gets the SAME
    # 4 comprehensive tables + charts as the other tabs. No more old build_yoy_table.
    yoy_sections: list[dict] = []
    if isinstance(yoy_result, dict) and yoy_result.get("status") == "ok":
        yoy_groups = yoy_result.get("groups") or []
        if yoy_groups:
            sub_tabs = []
            for g in yoy_groups:
                q_label = g.get("quarter", "")
                q_periods = g.get("periods") or []
                if not q_periods:
                    continue
                # [v17] Rename "Q4" → "T4", "Q1" → "T1", etc.
                t_label = q_label.replace("Q", "T") if q_label.startswith("Q") else q_label
                # [v18] Build comprehensive tables from YoY periods.
                # Pass quarterly statement results so accounts-based rows
                # (Ativo Circ, Passivo, etc.) have data. The YoY period
                # labels are like "4T2025" which match the quarterly
                # statement result period labels.
                yoy_tables = build_comprehensive_period_table(
                    q_periods, t_label,
                    bpa_result=bpa_result_q, bpp_result=bpp_result_q,
                    dre_result=dre_result_q, dfc_result=dfc_result_q,
                    capex_map=capex_map)
                yoy_secs = list(yoy_tables)
                # Add trend chart (Receita/EBITDA/Lucro bars)
                yoy_chart = build_period_chart(q_periods, t_label)
                if yoy_chart:
                    yoy_secs.append(yoy_chart)
                # Add margins bar chart
                yoy_margins = build_period_margins_chart(q_periods, t_label)
                if yoy_margins:
                    yoy_secs.append(yoy_margins)
                # [v25] Add indicator charts
                try:
                    yoy_ind = build_indicator_charts(q_periods, t_label, bpa_result=bpa_result_q, bpp_result=bpp_result_q, capex_map=capex_map)
                    yoy_secs.extend(yoy_ind)
                except Exception as e:
                    print(f"[financials] YoY indicator charts failed: {e}", flush=True)
                sub_tabs.append({"name": t_label, "sections": yoy_secs})

            if sub_tabs:
                yoy_sections = [{"type": "subtabs", "tabs": sub_tabs}]

    if not yoy_sections:
        yoy_sections = [build_error_section("Trimestral YoY", yoy_result.get("error", "unknown") if isinstance(yoy_result, dict) else "unknown")]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Trimestral YoY ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Assemble the dashboard payload with sidebar groups ────────────────
    tabs = [
        # RESUMO
        {"name": "Overview",      "group": "Resumo",            "sections": overview_sections},
        {"name": "Indicadores",   "group": "Resumo",            "sections": [indicadores_section]},
        {"name": "Crescimento",   "group": "Resumo",            "sections": crescimento_sections},
        # DEMONSTRAÇÕES
        {"name": "Balanço",       "group": "Demonstrações",     "sections": balanco_sections},
        {"name": "DRE",           "group": "Demonstrações",     "sections": dre_sections},
        {"name": "DFC",           "group": "Demonstrações",     "sections": dfc_sections},
        {"name": "DVA",           "group": "Demonstrações",     "sections": dva_sections},
        # PERÍODOS
        {"name": "Anual",         "group": "Períodos",          "sections": anual_sections},
        {"name": "Trimestral QoQ", "group": "Períodos",          "sections": trimestral_sections},
        # SÉRIES TEMPORAIS
        {"name": "Anualizado",    "group": "Séries Temporais",  "sections": ttm_sections},
        {"name": "Trimestral YoY", "group": "Séries Temporais", "sections": yoy_sections},
    ]

    # Freshness footer
    freshness_footer = ""
    try:
        from skills._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness()
        last_period = get_last_synced_period()
        dfp_sync = fresh.get("dfp", "")
        itr_sync = fresh.get("itr", "")
        dfp_period = last_period.get("dfp", "")
        itr_period = last_period.get("itr", "")
        freshness_footer = (
            f"DFP: {dfp_sync[:10] if dfp_sync else '—'} (até {dfp_period or '—'}) • "
            f"ITR: {itr_sync[:10] if itr_sync else '—'} (até {itr_period or '—'})"
        )
    except Exception:
        pass

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[financials] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {
        "status": "ok",
        "company": company,
        "company_header": company_header,  # [v1.16.1] reuse, don't re-call
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }


# ── Statement-mode call helpers ──────────────────────────────────────────────

def _fetch_all_statements(
    company: str, consolidado: int, period: str = "annual",
) -> tuple:
    """[v1.2 / v1.24] Single-fetch: get ALL 5 statements in ONE SQL query, then reshape.

    Replaces 5 separate _call_bpa/_call_bpp/_call_dre/_call_dfc/_call_dva calls
    (each doing 3 SQL round-trips = 15 total) with a single fetch (3 round-trips).

    [v1.24] Now accepts a ``period`` parameter:
      - ``"annual"`` (default): calls ``_fetch_all_statements_annual(periods=4)``.
      - ``"quarterly"``: calls ``_fetch_all_statements_quarterly(periods=20)``
        which fetches ITR cumulative (meses IN 3/6/9) + DFP annual (meses=12)
        and derives standalone flow values (DRE/DFC/DVA = curr_cum − prev_cum).
        BPA/BPP are snapshot (direct period-end values).

    Backward-compatible: callers that don't pass ``period`` get annual (the
    pre-v1.24 behavior).

    Returns: (bpa_result, bpp_result, dre_result, dfc_result, dva_result)
    Each result has the same structure as the corresponding mode function.
    """
    from skills.cvm.financials.modes._statement_sections import (
        bpa_section_for, bpp_section_for, dre_section_for,
        dfc_section_for, dva_section_for, reshape_statement_periods,
    )

    if period == "quarterly":
        from skills.cvm.financials.fetchers import _fetch_all_statements_quarterly
        all_data = _fetch_all_statements_quarterly(company, consolidado, periods=20)
    else:
        from skills.cvm.financials.fetchers import _fetch_all_statements_annual
        all_data = _fetch_all_statements_annual(company, consolidado, periods=10)

    # If the fetch itself failed (not_found/not_synced), return error for all 5
    if all_data.get("status") != "ok" and "status" in all_data:
        err = all_data
        return err, err, err, err, err

    # Reshape each statement (same as the mode functions do)
    bpa_raw = all_data.get("BPA", {"status": "not_found"})
    bpp_raw = all_data.get("BPP", {"status": "not_found"})
    dre_raw = all_data.get("DRE", {"status": "not_found"})
    dfc_raw = all_data.get("DFC_MI", {"status": "not_found"})
    dva_raw = all_data.get("DVA", {"status": "not_found"})

    bpa_result = reshape_statement_periods(bpa_raw, section_fn=bpa_section_for, statement_label="BPA") if bpa_raw.get("status") == "ok" else bpa_raw
    bpp_result = reshape_statement_periods(bpp_raw, section_fn=bpp_section_for, statement_label="BPP") if bpp_raw.get("status") == "ok" else bpp_raw
    dre_result = reshape_statement_periods(dre_raw, section_fn=dre_section_for, statement_label="DRE") if dre_raw.get("status") == "ok" else dre_raw
    dfc_result = reshape_statement_periods(dfc_raw, section_fn=dfc_section_for, statement_label="DFC") if dfc_raw.get("status") == "ok" else dfc_raw
    dva_result = reshape_statement_periods(dva_raw, section_fn=dva_section_for, statement_label="DVA") if dva_raw.get("status") == "ok" else dva_raw

    return bpa_result, bpp_result, dre_result, dfc_result, dva_result
