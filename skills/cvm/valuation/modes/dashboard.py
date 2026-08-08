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
        # [v1.8] Growth metrics from compute_all_ratios() may return None
        # if the calculations engines don't have enough historical data.
        # Fetch annual periods from financials (like the financials dashboard
        # does) and pass them to the growth builder as a fallback.
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

        # [v2.2] V4 — Graham Number horizontal line overlay on the price chart.
        # If we have a Graham Number from ratios_dict, append it as a second
        # line dataset (horizontal line) on the historical price chart.
        if price_chart and isinstance(ratios_dict, dict):
            graham_val = ratios_dict.get("graham_number")
            if graham_val is not None:
                try:
                    graham_val = float(graham_val)
                    chart_data = price_chart.get("chart_data") or {}
                    data_block = chart_data.get("data") or {}
                    labels = data_block.get("labels") or []
                    datasets = data_block.get("datasets") or []
                    datasets.append({
                        "label": "Graham Number",
                        "data": [graham_val] * len(labels),
                        "borderColor": "#ef4444",
                        "type": "line",
                        "fill": False,
                        "tension": 0,
                        "pointRadius": 0,
                        "borderWidth": 2,
                        "borderDash": [8, 4],
                    })
                    data_block["datasets"] = datasets
                    chart_data["data"] = data_block
                    price_chart["chart_data"] = chart_data
                    # Re-sync the full-price snapshot used by the
                    # client-side range selector so the Graham line also
                    # appears when the user filters to 5A/1A/1M.
                    full_labels = price_chart.get("price_full_labels") or labels
                    price_chart["price_full_labels"] = full_labels
                except (TypeError, ValueError):
                    pass

        _hdr_elapsed = (_dt.now() - _hdr_start).total_seconds()
        print(f"[valuation] Header+chart done ({_hdr_elapsed:.1f}s).", flush=True)

    # ── Build sections ──────────────────────────────────────────────────
    print(f"[valuation] Building dashboard sections...", flush=True)
    kpis = build_overview_kpis(ratios_dict)
    overview_sections = _safe_build(build_overview_sections, ratios_dict)

    if company_header.get("name"):
        overview_sections.insert(0, {
            "type": "company_info",
            "company_header": company_header,
        })
    if price_chart:
        overview_sections.insert(1, price_chart)

    # [v1.8] Multiples: split by group + per-share merged in.
    # [v2.2] Wrap the 3 multiple groups + per-share into 3 subtabs.
    print(f"[valuation]   Multiples tab...", flush=True)
    multiples_sections = _safe_build(build_multiples_sections, ratios_dict)
    per_share_sections = _safe_build(build_per_share_sections, ratios_dict)

    # Split multiples_sections by title into the 3 groups.
    # build_multiples_sections returns (in order):
    #   [0] "Múltiplos de Preço" table
    #   [1] "Múltiplos de Preço — Comparativo" chart (optional)
    #   [2] "Múltiplos EV (Enterprise Value)" table
    #   [3] "Múltiplos EV — Comparativo" chart (optional)
    #   [4] "Múltiplos Menos Comuns" table
    price_secs: list[dict] = []
    ev_secs: list[dict] = []
    less_secs: list[dict] = []
    for s in multiples_sections:
        title = (s.get("title") or "").lower()
        if "ev" in title and "menos" not in title:
            ev_secs.append(s)
        elif "menos comuns" in title:
            less_secs.append(s)
        else:
            price_secs.append(s)
    # Per-share sections go in the "Preço" subtab.
    price_secs.extend(per_share_sections)

    multiples_tab_sections: list[dict] = []
    if price_secs or ev_secs or less_secs:
        multiples_subtabs: list[dict] = []
        if price_secs:
            multiples_subtabs.append({"name": "Preço", "sections": price_secs})
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

    # [v1.8] Profitability: split charts (Returns + Margins).
    # [v2.2] Wrap in 2 subtabs (Retornos + Margens). Add V5 ROE trend chart
    # to the Retornos subtab.
    print(f"[valuation]   Profitability tab...", flush=True)
    profitability_sections = _safe_build(build_profitability_section, ratios_dict)

    # Split: items 0-1 = Returns (ratio_grid + chart), items 2-3 = Margins.
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

    # V5 — ROE / ROA / ROIC 5Y trend chart goes in the Retornos subtab.
    try:
        roe_trend = build_roe_trend_chart(company, annual_periods)
        if roe_trend:
            ret_secs.append(roe_trend)
    except Exception as e:
        print(f"[valuation] ROE trend chart failed: {e}", flush=True)

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

    # [v1.8] Liquidity & Leverage: charts + detailed table (was collapsible).
    # [v2.2] Wrap in 2 subtabs (Liquidez + Endividamento).
    print(f"[valuation]   Liquidity & Leverage tab...", flush=True)
    liquidity_leverage_sections = _safe_build(
        build_liquidity_leverage_sections, ratios_dict)

    # Split: sections before the Leverage ratio_grid = Liquidez, sections
    # from the Leverage ratio_grid onwards = Endividamento.
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

    # [v1.8] Efficiency & Growth: split growth + charts + annual periods fallback.
    # [v2.2] Wrap in 2 subtabs (Eficiência + Crescimento).
    print(f"[valuation]   Efficiency & Growth tab...", flush=True)
    efficiency_growth_sections = _safe_build(
        build_efficiency_growth_sections, ratios_dict, annual_periods)

    # Split: the first section is the Efficiency table; everything from the
    # first "Crescimento" table onwards is Growth.
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

    # ── Freshness footer ────────────────────────────────────────────────
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
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

    # [v3] Dropped Histórico tab — it duplicated the historical skill and
    # took 20 minutes (fetching 5Y history for 9 metrics, each calling
    # history_fn). The historical skill already provides this functionality
    # with better performance (parallel fetching + cache).

    # [v2.1] DCF + IRR — Valor Intrínseco tab
    print(f"[valuation]   Valor Intrínseco tab...", flush=True)
    intrinsic_sections: list[dict] = []
    try:
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import (
            dcf_intrinsic_value_at, dcf_margin_of_safety_at,
        )
        from skills.cvm.calculations.metrics.irr import irr_at
        from skills.cvm.calculations.metrics.wacc import wacc_at
        from datetime import datetime as _vdt
        _vtoday = _vdt.now().strftime("%Y-%m-%d")

        intrinsic = dcf_intrinsic_value_at(company, _vtoday)
        mos = dcf_margin_of_safety_at(company, _vtoday)
        irr_val = irr_at(company, _vtoday)
        wacc_val = wacc_at(company, _vtoday)

        # Get current price for comparison
        price_val = ratios_dict.get("price") or ratios_dict.get("preco")

        rows = []
        if intrinsic is not None:
            rows.append([
                {"text": "DCF Valor Intrínseco", "tooltip": _get_tooltip("dcf_intrinsic_value")},
                f"R$ {intrinsic:.2f}",
            ])
        if price_val is not None:
            rows.append([
                {"text": "Preço Atual", "tooltip": "Preço atual da ação no mercado (COTAHIST)"},
                f"R$ {float(price_val):.2f}",
            ])
        if mos is not None:
            mos_pct = mos * 100
            assessment = "Subavaliado" if mos > 0.25 else ("Justo" if mos > 0 else "Supervalorizado")
            rows.append([
                {"text": "Margem de Segurança", "tooltip": _get_tooltip("dcf_margin_of_safety")},
                f"{mos_pct:.1f}% ({assessment})",
            ])
        if irr_val is not None:
            irr_pct = irr_val * 100
            rows.append([
                {"text": "TIR (IRR)", "tooltip": _get_tooltip("irr")},
                f"{irr_pct:.1f}%",
            ])
        if wacc_val is not None:
            wacc_pct = wacc_val * 100
            rows.append([
                {"text": "WACC", "tooltip": _get_tooltip("wacc")},
                f"{wacc_pct:.1f}%",
            ])
            if irr_val is not None:
                spread = (irr_val - wacc_val) * 100
                verdict = "Cria valor (TIR > WACC)" if irr_val > wacc_val else "Destrói valor (TIR < WACC)"
                rows.append([
                    {"text": "TIR - WACC", "tooltip": "Spread entre retorno esperado e custo de capital. >0 = cria valor."},
                    f"{spread:.1f}% ({verdict})",
                ])

        if rows:
            intrinsic_sections.append({
                "title": "Valor Intrínseco — DCF + TIR",
                "description": "DCF: fluxo de caixa descontado a 5 anos + valor terminal (crescimento = IPCA 12M). TIR: taxa de retorno anualizada ao preço atual.",
                "type": "table",
                "columns": ["Métrica", "Valor"],
                "rows": rows,
                "note": "Premissas: crescimento FCF = revenue_growth_1y, crescimento terminal = IPCA 12M, período = 5 anos, desconto = WACC.",
            })

            # Add to overview sections too
            overview_sections.append(intrinsic_sections[-1])

        # [v2.2] V3 — DCF Sensitivity Analysis (5 growth-rate scenarios).
        # Adds a table + bar chart showing how the intrinsic value responds
        # to FCF growth assumptions (base ± 2.5% and ± 5%).
        try:
            sensitivity_sections = build_dcf_sensitivity_section(company, _vtoday)
            if sensitivity_sections:
                intrinsic_sections.extend(sensitivity_sections)
        except Exception as e:
            print(f"[valuation] DCF sensitivity failed: {e}", flush=True)

    except Exception as e:
        print(f"[valuation] DCF/IRR failed: {e}", flush=True)

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
