"""Mode: dashboard -- multi-tab dividends dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:   KPI cards (Total Dividends Paid, Dividend Yield, Payout
                Ratio, Last Payment Date) + a Summary text section
  - History:    table of recent B3 dividend events (date, type, value per
                share, related-to)
  - Annual:     table of annual dividend summaries (year, Dividendos, JCP,
                Total Remuneração)

This mode does NOT fetch new data -- it calls ``summary()`` and reshapes
its output into a multi-tab payload. If ``summary()`` itself fails (e.g.
no company), the dashboard propagates the error dict instead of rendering
empty tabs.

The section-building helpers live in skills.cvm.dividends.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.dividends._registry import register_mode
from skills.cvm.dividends.modes.summary import summary
from skills.cvm.dividends.report import (
    build_overview_kpis,
    build_overview_section,
    build_history_section,
    build_annual_section,
    build_dividend_history_chart,
    build_annual_dividend_chart,
    build_annual_dividend_stacked_chart,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab dividends dashboard (thin composition of summary()). Tabs: "
        "Overview (4 KPI cards: Total Dividends Paid, Dividend Yield, Payout "
        "Ratio, Last Payment Date + Summary text), History (recent B3 events "
        "table), Annual (DVA 7.08.04.* per fiscal year). Optimized for the "
        "report tool's dashboard action."
    ),
    params={
        "company": "str. B3 ticker (PETR4). Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """Multi-tab dividends dashboard (thin composition of summary()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:   KPI cards (Total Dividends Paid, Dividend Yield, Payout
                    Ratio, Last Payment Date) + a Summary text section
      - History:    table of recent B3 dividend events (date, type, value per
                    share, related-to)
      - Annual:     table of annual dividend summaries (year, Dividendos,
                    JCP, Total Remuneração)

    This mode does NOT fetch new data -- it calls ``summary()`` and reshapes
    its output into a multi-tab payload. If ``summary()`` itself fails (e.g.
    no company), the dashboard propagates the error dict instead of
    rendering empty tabs.

    Args:
        company: B3 ticker (PETR4). Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no company), returns the ``summary()`` error
        dict verbatim.
    """
    # ── Gather underlying data (summary, wrapped defensively) ──
    print(f"[dividends] Starting dividends dashboard for company='{company}'...",
          flush=True)
    print(f"[dividends] Fetching summary data (history + annual + payable)...",
          flush=True)
    try:
        s = summary(company=company)
    except Exception as e:
        return {"status": "error",
                "sub_domain": "dividends", "mode": "dashboard",
                "error": str(e)}

    # Propagate validation errors (no company) as-is rather than rendering
    # empty tabs.
    if s.get("status") != "ok":
        return s

    sections = s.get("sections") or {}
    recent_events = sections.get("recent_events") or {}
    annual_trend = sections.get("annual_trend") or {}
    events_list = recent_events.get("events") or []
    periods_list = annual_trend.get("periods") or []
    print(f"[dividends] Data fetched: {len(events_list)} recent events, "
          f"{len(periods_list)} annual periods.", flush=True)

    # ── Top-level KPI cards (Total Dividends Paid, Div Yield, Payout Ratio,
    #     Last Payment Date) ──
    print(f"[dividends] Building KPI cards + tab sections...", flush=True)
    kpis = build_overview_kpis(s, company=company)

    # ── Build company header + price chart (v3 dashboard pattern) ──
    print(f"[dividends] Building company header + price chart...", flush=True)
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

    # ── Tab 1: Overview -- header + price chart + Summary text ──
    print(f"[dividends]   Overview...", flush=True)
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info",
                                   "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    overview_sections.append(build_overview_section(s))

    # ── Tab 2: History -- recent B3 dividend events table + line chart ──
    print(f"[dividends]   History...", flush=True)
    history_sections = [build_history_section(s)]
    history_chart = build_dividend_history_chart(events_list)
    if history_chart:
        history_sections.append(history_chart)

    # ── Tab 3: Annual -- DVA 7.08.04.* per fiscal year table + bar chart ──
    print(f"[dividends]   Annual...", flush=True)
    annual_sections = [build_annual_section(s)]
    annual_chart = build_annual_dividend_chart(periods_list)
    if annual_chart:
        annual_sections.append(annual_chart)
    # [v3] Add a stacked Dividendo vs JCP per year chart.
    stacked_chart = build_annual_dividend_stacked_chart(periods_list)
    if stacked_chart:
        annual_sections.append(stacked_chart)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Proventos.
    tabs = [
        {"name": "Overview", "group": "Resumo",    "sections": overview_sections},
        {"name": "History",  "group": "Proventos", "sections": history_sections},
        {"name": "Annual",   "group": "Proventos", "sections": annual_sections},
    ]
    print(f"[dividends] Done! {len(tabs)} tabs, {len(kpis)} KPIs, "
          f"{len(events_list)} events.", flush=True)

    # ── Freshness footer (DFP + ITR + COTAHIST sync dates) ──
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

    return {
        "status": "ok",
        "company": s.get("company", company),
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
