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
    build_error_section,
    build_ttm_chart,
    build_ttm_table,
    build_yoy_chart,
    build_yoy_table,
    build_period_table,
    build_period_chart,
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
            return _safe_call(annual, company=company, periods=6, consolidado=consolidado)

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

        tasks = {
            "annual": _fetch_annual,
            "quarterly": _fetch_quarterly,
            "statements": _fetch_statements,
            "statements_q": _fetch_statements_q,
            "ttm": _fetch_ttm,
            "yoy": _fetch_yoy,
            "ratios": _fetch_ratios,
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
        with ThreadPoolExecutor(max_workers=7) as executor:
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

        latest_annual_period: dict | None = None
        annual_periods: list[dict] = []
        if annual_payload.get("status") == "ok" and annual_payload.get("periods"):
            annual_periods = annual_payload["periods"]
            latest_annual_period = annual_periods[0]

        quarterly_periods: list[dict] = []
        if quarterly_payload.get("status") == "ok" and quarterly_payload.get("periods"):
            quarterly_periods = quarterly_payload["periods"]

        # [v2.1] Normalize TTM periods for use by flow-statement tabs (DRE/DFC/DVA).
        # Raw TTM periods (from ttm.py mode) have:
        #   - ``period_range`` (e.g. "Q3 2025 – Q2 2026")
        #   - ``ttm_date``    (e.g. "2026-06-30")
        #   - ``quarter``     (e.g. "2T2026") — used by build_ttm_table for labels
        #   - ``metrics``     (dict: receita_liquida, ebitda, lucro_liquido, fco, fci, fcf, ...)
        #   - ``ratios``      (dict: marg_*, roe, ...)
        # Trend-chart builders (build_statement_trend_chart / build_dfc_trend_chart /
        # build_dva_trend_chart) read ``p.get("period")`` for sorting + labels, so we
        # add a ``period`` key (= the quarter label) — both keys coexist, satisfying
        # ``build_ttm_table`` (uses ``quarter``) + the trend-chart builders (use
        # ``period``). ``_period_sort_key`` handles "2T2026" via its data_fim_exerc
        # fallback OR via the period label string sort.
        ttm_periods_normalized: list[dict] = []
        if isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
            for p in (ttm_result.get("periods") or []):
                quarter_label = p.get("quarter")
                if not quarter_label:
                    continue
                ttm_periods_normalized.append({
                    **p,
                    "period": quarter_label,
                })

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

    overview_sections = build_overview_sections(
        latest_annual_period, quarterly_periods, ratios_payload)

    if company_header.get("name"):
        overview_sections.insert(0, {
            "type": "company_info",
            "company_header": company_header,
        })

    # [v1.16.1] Historical price chart with time-range selector — top of Overview.
    price_chart = build_price_chart(company)
    if price_chart:
        overview_sections.insert(1, price_chart)

    # [v1.16.1] Annual trend chart (Receita/EBITDA/Lucro) — after price chart.
    # [v1.23 F2] Pass `company` so a year-end price overlay (right Y-axis,
    # purple dashed line) is rendered alongside the fundamentals.
    overview_trend = build_overview_trend_chart(annual_periods, company)
    if overview_trend:
        overview_sections.append(overview_trend)

    # [new commit] F14 — Accounting red flags (collapsible section at the
    # BOTTOM of Overview). Surfaces validation.py consistency checks +
    # ROE-negative-PL + FCO-3Y-decline checks. Wrapped in try/except so a
    # validation.py failure doesn't crash the Overview tab.
    try:
        red_flags = build_red_flags_section(
            bpa_result, bpp_result, dre_result, dfc_result, dva_result,
            annual_periods)
        if red_flags:
            overview_sections.append(red_flags)
    except Exception as e:
        print(f"[financials] Red flags section failed: {e}", flush=True)

    # [v2.0] WACC + DuPont + Altman Z sections (from ratios_payload).
    # These are point-in-time (no history_fn), so they're fast.
    try:
        wacc_sec = build_wacc_section(ratios_payload)
        if wacc_sec:
            overview_sections.append(wacc_sec)
    except Exception as e:
        print(f"[financials] WACC section failed: {e}", flush=True)
    try:
        dupont_sec = build_dupont_section(ratios_payload)
        if dupont_sec:
            overview_sections.append(dupont_sec)
    except Exception as e:
        print(f"[financials] DuPont section failed: {e}", flush=True)
    try:
        altman_sec = build_altman_z_section(ratios_payload)
        if altman_sec:
            overview_sections.append(altman_sec)
    except Exception as e:
        print(f"[financials] Altman Z section failed: {e}", flush=True)

    # [v1.22] Radar + Heatmap in Overview tab.
    try:
        radar = build_financials_radar(ratios_payload)
        if radar:
            overview_sections.append(radar)
    except Exception as e:
        print(f"[financials] Radar failed: {e}", flush=True)
    try:
        heatmap = build_financials_heatmap(ratios_payload)
        if heatmap:
            overview_sections.append(heatmap)
    except Exception as e:
        print(f"[financials] Heatmap failed: {e}", flush=True)

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
        # build_balanco_decomp_charts returns 4 charts: BPA abs+pct then
        # BPP abs+pct. Slice into BPA [0:2] and BPP [2:4].
        decomp_annual = build_balanco_decomp_charts(bpa_result, bpp_result)
        bpa_charts_annual = decomp_annual[:2]
        bpp_charts_annual = decomp_annual[2:]

        # Quarterly versions (with quarterly args → uses quarterly periods).
        # Only built when both quarterly BPA + BPP are available.
        if bpa_result_q and bpp_result_q:
            completo_charts_quarterly = build_balanco_chart(
                bpa_result, bpp_result,
                bpa_result_q=bpa_result_q, bpp_result_q=bpp_result_q)
            decomp_quarterly = build_balanco_decomp_charts(
                bpa_result, bpp_result,
                bpa_result_q=bpa_result_q, bpp_result_q=bpp_result_q)
            bpa_charts_quarterly = decomp_quarterly[:2]
            bpp_charts_quarterly = decomp_quarterly[2:]
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
        # [v2.1] Pass `ttm_periods` so a 3rd TTM toggle panel is added (TTM
        # trend chart + TTM metrics table). Only flow statements get TTM.
        dre_sections = build_dre_sections(
            dre_result, annual_periods, latest_annual_period,
            company=company, dre_result_q=dre_result_q,
            quarterly_periods=quarterly_periods,
            ttm_periods=ttm_periods_normalized)
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
        # [v2.1] Pass `ttm_periods` so a 3rd TTM toggle panel is added.
        dfc_sections = build_dfc_sections(
            dfc_result, annual_periods, latest_annual_period,
            company=company, dfc_result_q=dfc_result_q,
            quarterly_periods=quarterly_periods,
            ttm_periods=ttm_periods_normalized)
    else:
        dfc_sections = [build_error_section("DFC", dfc_result.get("error", "unknown"))]
    # [new commit] F12 — DFC quality analysis (appended after existing DFC
    # sections). Engine-backed (capex_at + operating_cf_at + ttm_earnings_at)
    # wrapped in its own engine_cache_scope so the 3 engine calls share one
    # cache (the dashboard's outer scope already exited at this point).
    try:
        with engine_cache_scope():
            dfc_quality = build_dfc_quality_section(
                latest_annual_period, annual_periods, company, today)
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
        # [v2.1] Pass `ttm_periods` so a 3rd TTM toggle panel is added (TTM
        # metrics table; DVA TTM trend chart is None in v2.1 because TTM
        # periods don't have ``accounts``).
        dva_sections = build_dva_sections(
            dva_result, company=company, dva_result_q=dva_result_q,
            ttm_periods=ttm_periods_normalized)
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
    # Tab 8: Anual (raw annual periods table + trend chart)
    if annual_payload.get("status") == "ok":
        anual_sections = [build_period_table(annual_periods, "Anual")]
        anual_chart = build_period_chart(annual_periods, "Anual")
        if anual_chart:
            anual_sections.append(anual_chart)
    else:
        anual_sections = [build_error_section("Anual", annual_payload.get("error", "unknown"))]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Anual ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 9/11: Trimestral ──────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 9: Trimestral (raw quarterly periods table + bar chart)
    if quarterly_payload.get("status") == "ok":
        trimestral_sections = [build_period_table(quarterly_periods, "Trimestral")]
        trimestral_chart = build_period_chart(quarterly_periods, "Trimestral")
        if trimestral_chart:
            trimestral_sections.append(trimestral_chart)
    else:
        trimestral_sections = [build_error_section("Trimestral", quarterly_payload.get("error", "unknown"))]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Trimestral ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 10/11: Anualizado (TTM) ───────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 10: TTM (Anualizado)
    ttm_sections: list[dict] = []
    if isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
        ttm_periods = ttm_result.get("periods") or []
        if ttm_periods:
            ttm_sections.append(build_ttm_table(ttm_periods))
            ttm_chart = build_ttm_chart(ttm_periods)
            if ttm_chart:
                ttm_sections.append(ttm_chart)
    if not ttm_sections:
        ttm_sections = [build_error_section("Anualizado", ttm_result.get("error", "unknown") if isinstance(ttm_result, dict) else "unknown")]

    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Anualizado ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 11/11: Trimestral YoY ─────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # Tab 11: YoY Quarterly (Trimestral YoY)
    # [v1.18] build_yoy_table now returns a LIST of sections (one per year).
    yoy_sections: list[dict] = []
    if isinstance(yoy_result, dict) and yoy_result.get("status") == "ok":
        yoy_groups = yoy_result.get("groups") or []
        if yoy_groups:
            yoy_sections.extend(build_yoy_table(yoy_groups))
            yoy_chart = build_yoy_chart(yoy_groups)
            if yoy_chart:
                yoy_sections.append(yoy_chart)
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
        {"name": "Trimestral",    "group": "Períodos",          "sections": trimestral_sections},
        # SÉRIES TEMPORAIS
        {"name": "Anualizado",    "group": "Séries Temporais",  "sections": ttm_sections},
        {"name": "Trimestral YoY", "group": "Séries Temporais", "sections": yoy_sections},
    ]

    # Freshness footer
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
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
        all_data = _fetch_all_statements_annual(company, consolidado, periods=4)

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
