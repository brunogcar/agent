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
    print(f"[valuation]   Multiples tab...", flush=True)
    multiples_sections = _safe_build(build_multiples_sections, ratios_dict)
    per_share_sections = _safe_build(build_per_share_sections, ratios_dict)
    multiples_sections.extend(per_share_sections)

    # [v1.8] Profitability: split charts (Returns + Margins).
    print(f"[valuation]   Profitability tab...", flush=True)
    profitability_sections = _safe_build(build_profitability_section, ratios_dict)

    # [v1.8] Liquidity & Leverage: charts + detailed table (was collapsible).
    print(f"[valuation]   Liquidity & Leverage tab...", flush=True)
    liquidity_leverage_sections = _safe_build(
        build_liquidity_leverage_sections, ratios_dict)

    # [v1.8] Efficiency & Growth: split growth + charts + annual periods fallback.
    print(f"[valuation]   Efficiency & Growth tab...", flush=True)
    efficiency_growth_sections = _safe_build(
        build_efficiency_growth_sections, ratios_dict, annual_periods)

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
    # with better performance (parallel fetching + F7 cache).

    tabs = [
        {"name": "Overview",              "group": "Resumo",       "sections": overview_sections},
        {"name": "Múltiplos",             "group": "Resumo",       "sections": multiples_sections},
        {"name": "Rentabilidade",         "group": "Fundamentos",  "sections": profitability_sections},
        {"name": "Liquidez e Alavancagem",  "group": "Fundamentos",  "sections": liquidity_leverage_sections},
        {"name": "Eficiência e Crescimento",   "group": "Crescimento",  "sections": efficiency_growth_sections},
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
