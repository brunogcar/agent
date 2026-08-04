"""Mode: dashboard -- multi-tab insider trading dashboard (thin composition).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:            KPI cards (Sentimento, Volume Comprado,
                         Volume Vendido, Net Volume) + Summary text section
  - Recent Transactions: table of recent insider transactions (date, role,
                         type, asset, qty, price, volume)
  - By Role:             per-role table (Cargo, Transações, Qtd Comprada,
                         Qtd Vendida, Vol Comprado, Vol Vendido, Net Volume)
  - Monthly Net:         monthly net buy/sell table

This mode does NOT fetch new data -- it calls ``summary()``, ``history()``,
and ``by_role()`` and reshapes their output into a multi-tab payload.
Each sub-call is independently try/except-wrapped so a missing VLMO DB
degrades the corresponding tab to an error payload instead of crashing
the whole dashboard.

The section-building helpers live in skills.cvm.insider.report (so
they can be reused by other modes / tests). This module is the
orchestrator: gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.insider._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.insider._registry import register_mode
from skills.cvm.insider.modes.summary import summary
from skills.cvm.insider.modes.history import history
from skills.cvm.insider.modes.by_role import by_role
from skills.cvm.insider.report import (
    build_overview_kpis,
    build_overview_section,
    build_recent_transactions_section,
    build_by_role_section,
    build_by_role_chart,
    build_monthly_section,
    build_monthly_net_chart,
    build_cumulative_chart,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab insider trading dashboard (thin composition of summary() "
        "+ history() + by_role()). Tabs: Overview (4 KPI cards: Sentimento, "
        "Volume Comprado, Volume Vendido, Net Volume + Summary text), "
        "Recent Transactions (last 10 transactions table), By Role "
        "(per-role summary table), Monthly Net (monthly net buy/sell "
        "table). Optimized for the report tool's dashboard action."
    ),
    params={
        "company": "str. Ticker, name, or CNPJ. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="insider", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """Multi-tab insider trading dashboard (thin composition of existing modes).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:            KPI cards (Sentimento, Volume Comprado,
                             Volume Vendido, Net Volume) + a Summary text
                             section
      - Recent Transactions: table of the 10 most recent insider
                             transactions
      - By Role:             per-role table (Cargo, Transações, bought/sold
                             quantities + volumes + net)
      - Monthly Net:         per-month net buy/sell table

    This mode does NOT fetch new data -- it calls ``summary()``,
    ``history()``, and ``by_role()`` and reshapes their output into a
    multi-tab payload. Each sub-call is independently try/except-wrapped
    so a missing VLMO DB degrades the corresponding tab to an error
    payload instead of crashing the whole dashboard.

    Args:
        company: Ticker, name, or CNPJ. Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no company), returns
        ``{"status": "error", "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[insider] Starting insider dashboard for {company}...", flush=True)

    # ── Gather underlying data (each call wrapped independently) ────────────
    # The dashboard degrades gracefully: if summary()/history()/by_role()
    # returns an error payload (e.g. not_synced, not_found), the corresponding
    # tab is built from the error payload (sections will be empty or show a
    # status row via the adapter's _error_table fallback).
    print(f"[insider] Fetching summary()...", flush=True)
    summary_payload: dict = {}
    try:
        summary_payload = summary(company=company)
    except Exception as e:
        summary_payload = {"status": "error", "error": str(e)}

    print(f"[insider] Fetching history() (limit=10)...", flush=True)
    history_payload: dict = {}
    try:
        history_payload = history(company=company, limit=10)
    except Exception as e:
        history_payload = {"status": "error", "error": str(e)}

    print(f"[insider] Fetching by_role()...", flush=True)
    by_role_payload: dict = {}
    try:
        by_role_payload = by_role(company=company)
    except Exception as e:
        by_role_payload = {"status": "error", "error": str(e)}

    # ── Top-level KPI cards (Sentimento, Volume Comprado, Volume Vendido,
    #     Net Volume) ─────────────────────────────────────────────────────────
    print(f"[insider] Building dashboard sections...", flush=True)
    kpis = build_overview_kpis(summary_payload)

    # ── Build company header + price chart (v3 dashboard pattern) ──
    print(f"[insider] Building company header + price chart...", flush=True)
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

    # ── Tab 1: Overview -- header + price chart + Summary text ──
    print(f"[insider]   Overview...", flush=True)
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info",
                                   "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    overview_sections.append(build_overview_section(summary_payload))

    # ── Tab 2: Recent Transactions -- last 10 transactions table + cumulative chart ──
    print(f"[insider]   Recent Transactions...", flush=True)
    recent_sections = [build_recent_transactions_section(history_payload)]
    cumulative_chart = build_cumulative_chart(history_payload)
    if cumulative_chart:
        recent_sections.append(cumulative_chart)

    # ── Tab 3: By Role -- per-role summary table + buy/sell grouped chart ──
    print(f"[insider]   By Role...", flush=True)
    by_role_sections = [build_by_role_section(by_role_payload)]
    # [v3] Add a grouped bar chart showing buy vs sell volume per Cargo.
    by_role_chart = build_by_role_chart(by_role_payload)
    if by_role_chart:
        by_role_sections.append(by_role_chart)

    # ── Tab 4: Monthly Net -- monthly net buy/sell table + monthly net chart ──
    print(f"[insider]   Monthly Net...", flush=True)
    monthly_sections = [build_monthly_section(summary_payload)]
    monthly_chart = build_monthly_net_chart(summary_payload)
    if monthly_chart:
        monthly_sections.append(monthly_chart)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Transações / Análise.
    tabs = [
        {"name": "Overview",            "group": "Resumo",     "sections": overview_sections},
        {"name": "Recent Transactions", "group": "Transações", "sections": recent_sections},
        {"name": "By Role",             "group": "Transações", "sections": by_role_sections},
        {"name": "Monthly Net",         "group": "Análise",    "sections": monthly_sections},
    ]

    print(f"[insider] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)

    # Prefer the summary() result's company/cnpj when present (matches what
    # the Overview text section uses); fall back to the input company.
    company_out = (summary_payload.get("company")
                   or history_payload.get("company")
                   or by_role_payload.get("company")
                   or company)

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
        "company": company_out,
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
