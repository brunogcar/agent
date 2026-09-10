"""Mode: dashboard -- valuation dashboard with sidebar groups (thin composition).

[v1.8] Dashboard v2: split tables by related items, add charts per group,
fix growth metrics via annual periods from financials, better print output.

5 tabs grouped into 3 sidebar sections:
  RESUMO:
    - Overview (company header + price chart + split metrics tables)
    - Multiples (split by Price/EV/Less-common groups + per-share table + charts)
  FUNDAMENTOS:
    - Profitability (ratio_grid + split charts: Returns + Margins)
    - Liquidity & Leverage (ratio_grid + charts + detailed table)
  CRESCIMENTO:
    - Efficiency & Growth (efficiency table + split growth tables + charts)

[v4] Section timers now use the one-line ratios pattern:
    [sections] 1/6 Overview (1.2s, total 1.2s)
  instead of the old two-line (start + done) pattern. The entire dashboard
  body is wrapped in engine_cache_scope() so DCF sensitivity (5 DCF calls)
  reuses cached FCF/WACC/shares from the ratios fetch — fixes the Valor
  Intrínseco slowness regression.

Registered as "dashboard" in skills.cvm.valuation._registry.MODES.
"""
from __future__ import annotations

from skills._base import engine_cache_scope
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip
from skills.cvm.valuation._registry import register_mode
from skills.cvm.valuation.modes.ratios import ratios
from skills.cvm.valuation.report import (
    build_overview_kpis,
    build_overview_sections,
    build_multiples_sections,
    build_per_share_sections,
    build_profitability_section,
    build_liquidity_leverage_sections,
    build_efficiency_growth_sections,
    build_dcf_sensitivity_section,
    build_roe_trend_chart,
    build_pl_lpa_pvp_vpa_history_chart,
    build_margin_trend_chart,
    build_valuation_radar,
    build_valuation_heatmap,
    build_price_multiples_history_chart,
    build_ebit_multiples_history_chart,
    build_ebitda_multiples_history_chart,
    build_price_to_balance_history_chart,
    build_asset_to_price_history_chart,
    build_margins_horizons_chart,
    build_growth_evolution_charts,
    _fmt,
    _safe_get,
)


def _safe_build(fn, *args):
    """Call a section builder, returning an error-section list on failure."""
    try:
        sections = fn(*args)
        if not isinstance(sections, list):
            if isinstance(sections, dict):
                return [sections]
            return [{"type": "text",
                     "text": "Builder returned unexpected type: "
                             f"{type(sections).__name__}"}]
        return sections
    except Exception as e:
        print(f"[valuation] _safe_build({fn.__name__}) failed: {e}", flush=True)
        return [{"type": "text", "text": f"Section unavailable: {e}"}]


@register_mode(
    "dashboard",
    description=(
        "Multi-tab valuation dashboard with sidebar groups. 5 tabs in "
        "3 groups: Resumo (Overview, Multiples), Fundamentos "
        "(Profitability, Liquidity & Leverage), Crescimento "
        "(Efficiency & Growth). Company header + historical price chart "
        "at top of Overview. Tooltips on all ratio_grid items. Split "
        "tables + charts per group. Freshness footer."
    ),
    params={"company": "str. B3 ticker (PETR4). Required."},
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="valuation", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """5-tab valuation dashboard with sidebar groups."""
    if not company:
        return {"status": "error", "error": "company is required"}

    from datetime import datetime as _dt
    _t0 = _dt.now()
    print(f"[valuation] Starting dashboard for {company}...", flush=True)

    # [v4] ONE engine_cache_scope for the ENTIRE dashboard — ratios fetch,
    # section building, AND DCF sensitivity all share the same cache. This
    # fixes the Valor Intrínseco slowness: the 5 DCF sensitivity calls now
    # reuse cached FCF/WACC/shares from the ratios fetch instead of
    # re-querying the DB 5× each.
    with engine_cache_scope():
        # ── Fetch ratios ─────────────────────────────────────────────
        print(f"[valuation] Fetching ratios (via compute_all_ratios)...", flush=True)
        try:
            ratios_payload = ratios(company=company)
        except Exception as e:
            ratios_payload = {"status": "error", "error": str(e)}

        _r_elapsed = (_dt.now() - _t0).total_seconds()
        print(f"[valuation] Ratios fetched ({_r_elapsed:.1f}s)", flush=True)

        ratios_dict = (
            ratios_payload.get("ratios")
            if isinstance(ratios_payload, dict) else None
        )
        _n_metrics = (
            len([k for k in ratios_dict
                 if k not in ("status", "error", "date")])
            if isinstance(ratios_dict, dict) else 0
        )
        print(f"[valuation] Ratios computed: {_n_metrics} metrics.", flush=True)

        # ── Fetch annual periods for growth metrics ──────────────────
        print(f"[valuation] Fetching annual periods (for growth)...", flush=True)
        annual_periods: list[dict] = []
        try:
            from skills.cvm.financials.modes.annual import annual
            annual_payload = annual(company=company, periods=6, consolidado=1)
            if annual_payload.get("status") == "ok":
                annual_periods = annual_payload.get("periods") or []
                _ap_elapsed = (_dt.now() - _t0).total_seconds()
                print(f"[valuation] Annual periods: {len(annual_periods)} years ({_ap_elapsed:.1f}s).", flush=True)
            else:
                print(f"[valuation] Annual periods: unavailable ({annual_payload.get('error', '?')}).", flush=True)
        except Exception as e:
            print(f"[valuation] Annual periods: error ({e}).", flush=True)

        # ── Company header + price chart ─────────────────────────────
        _hdr_start = _dt.now()
        print(f"[valuation] Building company header + price chart...", flush=True)
        company_header = build_company_header(company)
        price_chart = build_price_chart(company)

        # [v1.10] Graham Number overlay REMOVED — the price chart now uses
        # the default shared build_price_chart() output unmodified.
        _hdr_elapsed = (_dt.now() - _hdr_start).total_seconds()
        print(f"[valuation] Header+chart done ({_hdr_elapsed:.1f}s).", flush=True)

        # ── Build sections (one-line timers, ratios pattern) ──────────
        # 6 sections: Overview, Multiples, Profitability, Liquidity &
        # Leverage, Efficiency & Growth, Valor Intrínseco.
        _SEC_TOTAL = 6
        _sec_count = 0
        _sec_t0 = _dt.now()

        # ── Section 1/6: Overview ────────────────────────────────────
        _sec_count += 1
        _s_t0 = _dt.now()
        kpis = build_overview_kpis(ratios_dict)
        overview_sections = _safe_build(build_overview_sections, ratios_dict)

        if company_header.get("name"):
            overview_sections.insert(0, {
                "type": "company_info",
                "company_header": company_header,
            })
        if price_chart:
            overview_sections.insert(1, price_chart)
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

        # ── Section 2/6: Multiples ───────────────────────────────────
        _sec_count += 1
        _s_t0 = _dt.now()
        multiples_sections = _safe_build(build_multiples_sections, ratios_dict)
        per_share_sections = _safe_build(build_per_share_sections, ratios_dict)

        # Split multiples_sections by title into groups.
        price_secs: list[dict] = []
        ev_secs: list[dict] = []
        less_secs: list[dict] = []
        ebit_ebitda_secs: list[dict] = []  # [v2.1] New EBIT/EBITDA subtab
        for s in multiples_sections:
            title = (s.get("title") or "").lower()
            if "menos comuns" in title:
                less_secs.append(s)
            elif "ev" in title:
                ev_secs.append(s)
            elif "ebit" in title or "ebitda" in title:
                ebit_ebitda_secs.append(s)
            else:
                price_secs.append(s)
        price_secs.extend(per_share_sections)

        # [v1.10] P/L, LPA, P/VP, VPA 5Y historical evolution chart.
        # [v2.1] Chart moved to the TOP of the Preço subtab (was appended last).
        try:
            pl_lpa_chart = build_pl_lpa_pvp_vpa_history_chart(company)
            if pl_lpa_chart:
                price_secs.insert(0, pl_lpa_chart)
        except Exception as e:
            print(f"[valuation] P/L-LPA history chart failed: {e}", flush=True)

        # [v2.1] New price-multiples evolution chart (PSR, P/RB, P/L, P/CG, P/DB).
        try:
            price_mult_chart = build_price_multiples_history_chart(company)
            if price_mult_chart:
                price_secs.insert(1, price_mult_chart)
        except Exception as e:
            print(f"[valuation] Price multiples history chart failed: {e}", flush=True)

        # [v2.1] New EBIT evolution chart at the top of the EBIT/EBITDA subtab.
        try:
            ebit_chart = build_ebit_multiples_history_chart(company)
            if ebit_chart:
                ebit_ebitda_secs.insert(0, ebit_chart)
        except Exception as e:
            print(f"[valuation] EBIT multiples history chart failed: {e}", flush=True)

        # [v2.1] New EBITDA evolution chart (2nd position in EBIT/EBITDA subtab).
        try:
            ebitda_chart = build_ebitda_multiples_history_chart(company)
            if ebitda_chart:
                ebit_ebitda_secs.insert(1, ebitda_chart)
        except Exception as e:
            print(f"[valuation] EBITDA multiples history chart failed: {e}", flush=True)

        # [v2.1] Split price-to-balance + asset-to-price evolution charts.
        try:
            ptb_chart = build_price_to_balance_history_chart(company)
            if ptb_chart:
                less_secs.insert(0, ptb_chart)
        except Exception as e:
            print(f"[valuation] Price-to-balance history chart failed: {e}", flush=True)
        try:
            atp_chart = build_asset_to_price_history_chart(company)
            if atp_chart:
                less_secs.insert(1, atp_chart)
        except Exception as e:
            print(f"[valuation] Asset-to-price history chart failed: {e}", flush=True)

        multiples_tab_sections: list[dict] = []
        if price_secs or ev_secs or less_secs or ebit_ebitda_secs:
            multiples_subtabs: list[dict] = []
            if price_secs:
                multiples_subtabs.append({"name": "Preço", "sections": price_secs})
            if ebit_ebitda_secs:
                multiples_subtabs.append({"name": "EBIT/EBITDA", "sections": ebit_ebitda_secs})
            if ev_secs:
                multiples_subtabs.append({"name": "EV", "sections": ev_secs})
            if less_secs:
                multiples_subtabs.append({"name": "Menos Comuns", "sections": less_secs})
            multiples_tab_sections = [{
                "type": "subtabs",
                "tabs": multiples_subtabs,
            }]
        else:
            multiples_tab_sections = []
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Múltiplos ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

        # ── Section 3/6: Profitability ───────────────────────────────
        _sec_count += 1
        _s_t0 = _dt.now()
        profitability_sections = _safe_build(build_profitability_section, ratios_dict)

        ret_secs: list[dict] = []
        mar_secs: list[dict] = []
        seen_returns_chart = False
        for s in profitability_sections:
            title = (s.get("title") or "").lower()
            if "margens" in title or "margin" in title:
                mar_secs.append(s)
            else:
                ret_secs.append(s)
                if s.get("type") == "chart":
                    seen_returns_chart = True

        # [v1.10] ROIC/ROE/ROA 5Y historical step-line chart (uses *_history()).
        # [v2.1] Chart moved to the TOP of the Retornos subtab (was appended last).
        try:
            roe_trend = build_roe_trend_chart(company)
            if roe_trend:
                ret_secs.insert(0, roe_trend)
        except Exception as e:
            print(f"[valuation] ROE trend chart failed: {e}", flush=True)

        # [v1.11] Margins 5Y historical step-line chart in Margens subtab.
        # [v2.1] Chart moved to the TOP of the Margens subtab (was appended last).
        #        Colors unified with financials (maroon/pink shades).
        try:
            margin_trend = build_margin_trend_chart(company)
            if margin_trend:
                mar_secs.insert(0, margin_trend)
        except Exception as e:
            print(f"[valuation] Margin trend chart failed: {e}", flush=True)

        # [v2.1] New margins × horizons chart (MB/ML at 3M/1A/5A + EBIT/EBITDA%).
        # Now returns 3 separate charts (EBIT, EBITDA, MB+ML).
        try:
            margins_charts = build_margins_horizons_chart(company)
            if margins_charts:
                for mc in margins_charts:
                    mar_secs.insert(1, mc)
        except Exception as e:
            print(f"[valuation] Margins horizons chart failed: {e}", flush=True)

        # [v1.11] Radar + Heatmap in Overview tab.
        try:
            radar = build_valuation_radar(ratios_dict)
            if radar:
                overview_sections.append(radar)
        except Exception as e:
            print(f"[valuation] Radar chart failed: {e}", flush=True)
        try:
            heatmap = build_valuation_heatmap(ratios_dict)
            if heatmap:
                overview_sections.append(heatmap)
        except Exception as e:
            print(f"[valuation] Heatmap failed: {e}", flush=True)

        profitability_tab_sections: list[dict] = []
        if ret_secs or mar_secs:
            prof_subtabs: list[dict] = []
            if ret_secs:
                prof_subtabs.append({"name": "Retornos", "sections": ret_secs})
            if mar_secs:
                prof_subtabs.append({"name": "Margens", "sections": mar_secs})
            profitability_tab_sections = [{
                "type": "subtabs",
                "tabs": prof_subtabs,
            }]
        else:
            profitability_tab_sections = []
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Rentabilidade ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

        # ── Section 4/6: Liquidity & Leverage ────────────────────────
        _sec_count += 1
        _s_t0 = _dt.now()
        liquidity_leverage_sections = _safe_build(
            build_liquidity_leverage_sections, ratios_dict)

        liq_secs: list[dict] = []
        lev_secs: list[dict] = []
        split_done = False
        for s in liquidity_leverage_sections:
            title = (s.get("title") or "").lower()
            if not split_done and ("alavancagem" in title or "leverage" in title):
                split_done = True
            if split_done:
                lev_secs.append(s)
            else:
                liq_secs.append(s)

        liquidity_tab_sections: list[dict] = []
        if liq_secs or lev_secs:
            liq_subtabs: list[dict] = []
            if liq_secs:
                liq_subtabs.append({"name": "Liquidez", "sections": liq_secs})
            if lev_secs:
                liq_subtabs.append({"name": "Endividamento", "sections": lev_secs})
            liquidity_tab_sections = [{
                "type": "subtabs",
                "tabs": liq_subtabs,
            }]
        else:
            liquidity_tab_sections = []
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Liquidez e Alavancagem ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

        # ── Section 5/6: Efficiency & Growth ─────────────────────────
        _sec_count += 1
        _s_t0 = _dt.now()
        efficiency_growth_sections = _safe_build(
            build_efficiency_growth_sections, ratios_dict, annual_periods)

        eff_secs: list[dict] = []
        grow_secs: list[dict] = []
        growth_split_done = False
        for s in efficiency_growth_sections:
            title = (s.get("title") or "").lower()
            if not growth_split_done and "crescimento" in title:
                growth_split_done = True
            if growth_split_done:
                grow_secs.append(s)
            else:
                eff_secs.append(s)

        # [v2.1] New growth evolution charts (RL, RB, LL with 3M/1A/5A).
        try:
            growth_charts = build_growth_evolution_charts(company)
        except Exception as e:
            print(f"[valuation] Growth evolution charts failed: {e}", flush=True)
            growth_charts = []

        # [v2.1] Restructure Crescimento into 4 self-contained sub-subtabs:
        #   Receita Líq.   — RL evolution chart + RL mini-table (3M/1Y/5Y) + RL bar chart
        #   Receita Bruta — RB evolution chart + RB mini-table + RB bar chart
        #   Lucro Líq.    — LL evolution chart + LL mini-table + LL bar chart
        #   Comparativo   — original per-horizon tables + comparison bar charts
        # Each metric subtab shows that metric's data end-to-end; the Comparativo
        # subtab preserves the cross-metric comparison view. The template now
        # supports nested subtabs (macros.html `subtabs` macro recurses).

        # Map each evolution chart to its metric by title.
        rl_evo = rb_evo = ll_evo = None
        for gc in growth_charts:
            gc_title = (gc.get("title") or "").lower()
            if "receita líquida" in gc_title:
                rl_evo = gc
            elif "receita bruta" in gc_title:
                rb_evo = gc
            elif "lucro líquido" in gc_title:
                ll_evo = gc

        # Per-metric growth definitions: (label, key_3m, key_1y, key_5y, color, evo_chart, tab_name)
        _METRIC_DEFS = [
            ("Receita Líquida", "revenue_growth_3m", "revenue_growth_1y", "revenue_growth_5y",
             "#f59e0b", rl_evo, "Receita Líq."),
            ("Receita Bruta", "gross_profit_growth_3m", "gross_profit_growth_1y", "gross_profit_growth_5y",
             "#d946a0", rb_evo, "Receita Bruta"),
            ("Lucro Líquido", "net_income_growth_3m", "net_income_growth_1y", "net_income_growth_5y",
             "#a855f7", ll_evo, "Lucro Líq."),
        ]
        _HORIZONS = [("3M", 0), ("1Y", 1), ("5Y", 5)]

        def _build_metric_subtab(metric_label, key_3m, key_1y, key_5y, color, evo_chart):
            """Build a self-contained subtab for one growth metric."""
            secs: list[dict] = []
            if evo_chart:
                secs.append(evo_chart)
            # Per-metric mini-table: 3 rows (3M, 1Y, 5Y) for this metric only.
            rows = []
            bar_labels: list[str] = []
            bar_values: list[float] = []
            for win_label, _ in _HORIZONS:
                key = key_3m if win_label == "3M" else key_1y if win_label == "1Y" else key_5y
                val = _safe_get(ratios_dict, key)
                formula = _get_tooltip(key) or f"Crescimento de {metric_label} {win_label}"
                rows.append([{"text": f"Crescimento {win_label}", "tooltip": formula},
                             _fmt(val, "pct")])
                if val is not None:
                    bar_labels.append(win_label)
                    bar_values.append(val * 100 if abs(val) < 1 else val)
            secs.append({
                "title": f"{metric_label} — Crescimento por Horizonte",
                "description": f"Crescimento de {metric_label} em 3 meses, 1 ano e 5 anos.",
                "type": "table",
                "columns": ["Horizonte", "Crescimento"],
                "rows": rows,
                "negative_red": True,
                "positive_green": True,
            })
            # Per-metric bar chart comparing the 3 horizons (same color as the
            # evolution chart so the subtab is visually cohesive).
            if len(bar_labels) >= 2:
                secs.append({
                    "type": "chart",
                    "title": f"{metric_label} — Comparativo de Horizontes",
                    "description": f"Crescimento de {metric_label}: 3M, 1Y e 5Y.",
                    "chart_data": {
                        "type": "bar",
                        "data": {"labels": bar_labels,
                                 "datasets": [{"label": metric_label, "data": bar_values,
                                               "backgroundColor": color}]},
                        "options": {"responsive": True, "maintainAspectRatio": False,
                                    "scales": {"y": {"beginAtZero": True}}},
                    },
                })
            return secs

        cres_subtabs: list[dict] = []
        for metric_label, k3m, k1y, k5y, color, evo, tab_name in _METRIC_DEFS:
            sub_secs = _build_metric_subtab(metric_label, k3m, k1y, k5y, color, evo)
            if sub_secs:
                cres_subtabs.append({"name": tab_name, "sections": sub_secs})

        # Comparativo subtab: keep ALL original per-horizon tables + comparison
        # bar charts (they compare Receita Líquida / Receita Bruta / Lucro
        # Líquido side by side at each horizon).
        if grow_secs:
            cres_subtabs.append({"name": "Comparativo", "sections": grow_secs})

        if cres_subtabs:
            grow_secs = [{"type": "subtabs", "tabs": cres_subtabs}]
        else:
            grow_secs = []

        efficiency_tab_sections: list[dict] = []
        if eff_secs or grow_secs:
            eg_subtabs: list[dict] = []
            if eff_secs:
                eg_subtabs.append({"name": "Eficiência", "sections": eff_secs})
            if grow_secs:
                eg_subtabs.append({"name": "Crescimento", "sections": grow_secs})
            efficiency_tab_sections = [{
                "type": "subtabs",
                "tabs": eg_subtabs,
            }]
        else:
            efficiency_tab_sections = []
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Eficiência e Crescimento ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

        # ── Section 6/6: Valor Intrínseco (DCF + IRR + Sensitivity) ──
        _sec_count += 1
        _s_t0 = _dt.now()
        intrinsic_sections: list[dict] = []
        try:
            from skills.cvm.calculations.metrics.dcf_intrinsic_value import (
                dcf_intrinsic_value_at, dcf_margin_of_safety_at,
            )
            from skills.cvm.calculations.metrics.irr import irr_at
            from skills.cvm.calculations.metrics.wacc import wacc_at
            _vtoday = _dt.now().strftime("%Y-%m-%d")

            intrinsic = dcf_intrinsic_value_at(company, _vtoday)
            mos = dcf_margin_of_safety_at(company, _vtoday)
            irr_val = irr_at(company, _vtoday)
            wacc_val = wacc_at(company, _vtoday)

            price_val = ratios_dict.get("price") or ratios_dict.get("preco")

            rows = []
            if intrinsic is not None:
                rows.append([
                    {"text": "DCF Valor Intrínseco", "tooltip": _get_tooltip("dcf_intrinsic_value")},
                    _fmt(intrinsic, "brl_full"),
                ])
            if price_val is not None:
                rows.append([
                    {"text": "Preço Atual", "tooltip": "Preço atual da ação no mercado (COTAHIST)"},
                    _fmt(float(price_val), "brl_full"),
                ])
            if mos is not None:
                assessment = "Subavaliado" if mos > 0.25 else ("Justo" if mos > 0 else "Supervalorizado")
                rows.append([
                    {"text": "Margem de Segurança", "tooltip": _get_tooltip("dcf_margin_of_safety")},
                    f"{_fmt(mos, 'pct')} ({assessment})",
                ])
            if irr_val is not None:
                rows.append([
                    {"text": "TIR (IRR)", "tooltip": _get_tooltip("irr")},
                    _fmt(irr_val, "pct"),
                ])
            if wacc_val is not None:
                rows.append([
                    {"text": "WACC", "tooltip": _get_tooltip("wacc")},
                    _fmt(wacc_val, "pct"),
                ])
                if irr_val is not None:
                    spread = irr_val - wacc_val
                    verdict = "Cria valor (TIR > WACC)" if irr_val > wacc_val else "Destrói valor (TIR < WACC)"
                    rows.append([
                        {"text": "TIR - WACC", "tooltip": "Spread entre retorno esperado e custo de capital. >0 = cria valor."},
                        f"{_fmt(spread, 'pct')} ({verdict})",
                    ])

            if rows:
                intrinsic_sections.append({
                    "title": "Valor Intrínseco — DCF + TIR",
                    "description": "DCF: fluxo de caixa descontado a 5 anos + valor terminal (crescimento = IPCA 12M). TIR: taxa de retorno anualizada ao preço atual.",
                    "type": "table",
                    "columns": ["Métrica", "Valor"],
                    "rows": rows,
                    "negative_red": True,
                    "positive_green": True,
                    "note": "Premissas: crescimento FCF = revenue_growth_1y, crescimento terminal = IPCA 12M, período = 5 anos, desconto = WACC.",
                })
                overview_sections.append(intrinsic_sections[-1])

            # [v1.9] DCF Sensitivity Analysis (5 growth-rate scenarios).
            # Now inside engine_cache_scope — the 5 _dcf_at_growth calls
            # reuse cached FCF/WACC/shares from the DCF call above.
            try:
                sensitivity_sections = build_dcf_sensitivity_section(company, _vtoday)
                if sensitivity_sections:
                    intrinsic_sections.extend(sensitivity_sections)
            except Exception as e:
                print(f"[valuation] DCF sensitivity failed: {e}", flush=True)

        except Exception as e:
            print(f"[valuation] DCF/IRR failed: {e}", flush=True)
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Valor Intrínseco ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Freshness footer ────────────────────────────────────────────────
    freshness_footer = ""
    try:
        from skills._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness()
        last = get_last_synced_period()
        dfp_sync = fresh.get("dfp", "")
        itr_sync = fresh.get("itr", "")
        cot_sync = fresh.get("cotahist", "")
        fre_sync = fresh.get("fre", "")
        dfp_period = last.get("dfp", "")
        itr_period = last.get("itr", "")
        freshness_footer = (
            f"DFP: {dfp_sync[:10] if dfp_sync else '—'} (até {dfp_period or '—'}) • "
            f"ITR: {itr_sync[:10] if itr_sync else '—'} (até {itr_period or '—'}) • "
            f"COTAHIST: {cot_sync[:10] if cot_sync else '—'} • "
            f"FRE: {fre_sync[:10] if fre_sync else '—'}"
        )
    except Exception:
        pass

    tabs = [
        {"name": "Overview",              "group": "Resumo",       "sections": overview_sections},
        {"name": "Múltiplos",             "group": "Resumo",       "sections": multiples_tab_sections},
        {"name": "Valor Intrínseco",      "group": "Resumo",       "sections": intrinsic_sections},
        {"name": "Rentabilidade",         "group": "Fundamentos",  "sections": profitability_tab_sections},
        {"name": "Liquidez e Alavancagem",  "group": "Fundamentos",  "sections": liquidity_tab_sections},
        {"name": "Eficiência e Crescimento",   "group": "Crescimento",  "sections": efficiency_tab_sections},
    ]
    _total = (_dt.now() - _t0).total_seconds()
    print(f"[valuation] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {
        "status": "ok",
        "company": company,
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
