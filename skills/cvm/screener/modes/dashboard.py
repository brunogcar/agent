"""Mode: dashboard -- multi-tab screener dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:    Summary text section (setor, peer_count, ticker being
                 compared, cheap/expensive labels summary)
  - Peers:       full peers table (sorted by P/L cheapest-first) with
                 valuation ratios + financials + segmento
  - Comparison:  per-metric table comparing the ticker vs sector medians
                 with cheap/expensive/above/below labels

This mode does NOT fetch new data -- it calls ``compare()`` (which
internally calls ``sector()``) and reshapes the results into a multi-tab
payload. The compare() call is wrapped in try/except so a partial failure
(e.g. ticker not found in bridge) still renders an Overview + Peers tab
(when sector() succeeds) and an empty Comparison tab.

The section-building helpers live in skills.cvm.screener.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.screener._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.screener._registry import register_mode
from skills.cvm.screener.modes.compare import compare
from skills.cvm.screener.report import (
    build_overview_kpis,
    build_overview_section,
    build_peers_section,
    build_comparison_section,
    build_comparison_chart,
    build_top_companies_chart,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab screener dashboard (thin composition of compare() + "
        "sector()). Tabs: Overview (Summary text + 5 top-level KPI cards: "
        "Median P/L, Median P/VPA, Median EV/EBITDA, Median ROE, Median "
        "Div Yield), Peers (full peers table sorted by P/L cheapest-first), "
        "Comparison (my ticker vs sector medians per metric with "
        "cheap/expensive/above/below labels). Optimized for the report "
        "tool's dashboard action."
    ),
    params={
        "company": "str. B3 ticker (e.g. 'SUZB3'). Required.",
        "limit":   "int. Max peers to fetch for median. Default: 20.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="screener", mode="dashboard", '
        'params=\'{"company":"SUZB3"}\')',
    ],
)
def dashboard(company: str = "", limit: int = 20) -> dict:
    """Multi-tab screener dashboard (thin composition of compare()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:    Summary text section
      - Peers:       full peers table
      - Comparison:  per-metric my vs sector table

    This mode does NOT fetch new data -- it calls ``compare()`` (which
    internally calls ``sector()``) and reshapes the results. The compare()
    call is wrapped in try/except so a partial failure still renders an
    Overview + Peers tab (when sector() succeeds) and an empty Comparison
    tab.

    Args:
        company: B3 ticker (e.g. "SUZB3"). Required.
        limit:   Max peers to fetch for median computation. Default: 20.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no company), returns
        ``{"status": "error", "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[screener] Starting screener dashboard for {company}...", flush=True)
    _t0 = _dt.now()

    # ── Gather underlying data: compare() (which internally calls sector()) ──
    print(f"[screener] Fetching compare() (limit={limit})...", flush=True)
    compare_payload: dict = {}
    try:
        compare_payload = compare(company=company, limit=limit)
    except Exception as e:
        compare_payload = {"status": "error", "error": str(e)}

    # [v3] Build company header + price chart once at the start so they're
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

    # Freshness footer (DFP + ITR + COTAHIST sync dates) — computed once so it
    # can be returned by both the happy path and the degraded early-return.
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness()
        last = get_last_synced_period()
        dfp_sync = fresh.get("dfp", "")
        itr_sync = fresh.get("itr", "")
        cot_sync = fresh.get("cotahist", "")
        dfp_period = last.get("dfp", "")
        itr_period = last.get("itr", "")
        freshness_footer = (
            f"DFP: {dfp_sync[:10] if dfp_sync else '—'} (até {dfp_period or '—'}) • "
            f"ITR: {itr_sync[:10] if itr_sync else '—'} (até {itr_period or '—'}) • "
            f"COTAHIST: {cot_sync[:10] if cot_sync else '—'}"
        )
    except Exception:
        pass

    # [v4] When compare() fails (not_found / error), still return status=ok
    # with the full 3-tab dashboard structure (Overview/Peers/Comparison) so
    # the HTML renders with the dashboard layout (KPI cards + tab nav). The
    # Overview tab shows the error message so the user knows WHY KPIs are
    # "—". This is better than returning a bare error with 1 tab (which
    # renders as "almost blank" in the HTML dashboard template).
    if compare_payload.get("status") != "ok":
        error_msg = compare_payload.get("error", "compare() failed")
        # [v3] Build Overview sections with header + price chart + error text.
        degraded_overview: list[dict] = []
        if company_header.get("name"):
            degraded_overview.append({"type": "company_info",
                                       "company_header": company_header})
        if price_chart:
            degraded_overview.append(price_chart)
        degraded_overview.append({
            "title": "Summary",
            "type": "text",
            "text": (
                f"Company: {company}\n"
                f"Status: {compare_payload.get('status', 'error')}\n"
                f"Error: {error_msg}\n\n"
                f"This usually means the ticker's sector has no peers "
                f"with valuation data, or the ticker was not found in "
                f"the bridge/CAD."
            ),
        })
        return {
            "status": "ok",  # render the dashboard structure
            "company": company,
            "company_header": company_header,
            "error": error_msg,  # keep error in payload for console output
            "tabs": [
                {"name": "Overview",   "group": "Resumo",  "sections": degraded_overview},
                {"name": "Peers",      "group": "Análise", "sections": [{
                    "title": "Peers (0)",
                    "type": "table",
                    "columns": ["Ticker", "P/L", "P/VPA", "EV/EBITDA", "ROE"],
                    "rows": [],
                    "formats": {"Ticker": "text", "P/L": "num",
                                "P/VPA": "num", "EV/EBITDA": "num", "ROE": "pct"},
                }]},
                {"name": "Comparison", "group": "Análise", "sections": [{
                    "title": "My Ticker vs Sector Medians",
                    "type": "table",
                    "columns": ["Metric", "My Value", "Sector Median", "vs Sector"],
                    "rows": [],
                    "formats": {"Metric": "text", "My Value": "text",
                                "Sector Median": "text", "vs Sector": "text"},
                }]},
            ],
            "kpis": [
                {"label": "Median P/L",       "value": "—", "unit": "num"},
                {"label": "Median P/VPA",     "value": "—", "unit": "num"},
                {"label": "Median EV/EBITDA", "value": "—", "unit": "num"},
                {"label": "Median ROE",       "value": "—", "unit": "pct"},
                {"label": "Median Div Yield", "value": "—", "unit": "pct"},
            ],
            "freshness_footer": freshness_footer,
        }

    # compare() succeeded — reconstruct sector payload from compare's fields.
    sector_payload: dict = {
        "status": "ok",
        "setor": compare_payload.get("setor", ""),
        "peer_count": compare_payload.get("peer_count", 0),
        "peers": compare_payload.get("peers", []),
        "medians": compare_payload.get("medians", {}),
    }

    medians = sector_payload.get("medians") or {}

    # ── Top-level KPI cards (5 sector medians) ──
    kpis = build_overview_kpis(medians, compare_payload.get("my_data"))

    # [v5] One-line section timers (ratios pattern): 3 sections.
    _SEC_TOTAL = 3
    _sec_count = 0
    _sec_t0 = _dt.now()

    # ── Section 1/3: Overview ──────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info",
                                   "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    overview_sections.append(build_overview_section(sector_payload, compare_payload))
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/3: Peers ─────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    peers_sections = [build_peers_section(sector_payload)]
    top_chart = build_top_companies_chart(sector_payload, metric="p_l")
    if top_chart:
        peers_sections.append(top_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Peers ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/3: Comparison ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    comparison_sections = [build_comparison_section(compare_payload)]
    # [v3] Add a grouped bar chart showing My Value vs Sector Median per metric.
    comp_chart = build_comparison_chart(compare_payload)
    if comp_chart:
        comparison_sections.append(comp_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Comparison ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Análise.
    tabs = [
        {"name": "Overview",    "group": "Resumo",  "sections": overview_sections},
        {"name": "Peers",       "group": "Análise", "sections": peers_sections},
        {"name": "Comparison",  "group": "Análise", "sections": comparison_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[screener] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)

    # Prefer compare()'s ticker (uppercased) for the company field; fall
    # back to the input company string.
    company_out = compare_payload.get("ticker") or company

    return {
        "status": "ok",
        "company": company_out,
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
