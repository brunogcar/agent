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

from skills.cvm.insider._registry import register_mode
from skills.cvm.insider.modes.summary import summary
from skills.cvm.insider.modes.history import history
from skills.cvm.insider.modes.by_role import by_role
from skills.cvm.insider.report import (
    build_overview_kpis,
    build_overview_section,
    build_recent_transactions_section,
    build_by_role_section,
    build_monthly_section,
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

    # ── Gather underlying data (each call wrapped independently) ────────────
    # The dashboard degrades gracefully: if summary()/history()/by_role()
    # returns an error payload (e.g. not_synced, not_found), the corresponding
    # tab is built from the error payload (sections will be empty or show a
    # status row via the adapter's _error_table fallback).
    summary_payload: dict = {}
    try:
        summary_payload = summary(company=company)
    except Exception as e:
        summary_payload = {"status": "error", "error": str(e)}

    history_payload: dict = {}
    try:
        history_payload = history(company=company, limit=10)
    except Exception as e:
        history_payload = {"status": "error", "error": str(e)}

    by_role_payload: dict = {}
    try:
        by_role_payload = by_role(company=company)
    except Exception as e:
        by_role_payload = {"status": "error", "error": str(e)}

    # ── Top-level KPI cards (Sentimento, Volume Comprado, Volume Vendido,
    #     Net Volume) ─────────────────────────────────────────────────────────
    kpis = build_overview_kpis(summary_payload)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ─
    overview_sections = [build_overview_section(summary_payload)]

    # ── Tab 2: Recent Transactions -- last 10 transactions table ──
    recent_sections = [build_recent_transactions_section(history_payload)]

    # ── Tab 3: By Role -- per-role summary table ──
    by_role_sections = [build_by_role_section(by_role_payload)]

    # ── Tab 4: Monthly Net -- monthly net buy/sell table ──
    monthly_sections = [build_monthly_section(summary_payload)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",            "sections": overview_sections},
        {"name": "Recent Transactions", "sections": recent_sections},
        {"name": "By Role",             "sections": by_role_sections},
        {"name": "Monthly Net",         "sections": monthly_sections},
    ]

    # Prefer the summary() result's company/cnpj when present (matches what
    # the Overview text section uses); fall back to the input company.
    company_out = (summary_payload.get("company")
                   or history_payload.get("company")
                   or by_role_payload.get("company")
                   or company)

    return {
        "status": "ok",
        "company": company_out,
        "tabs": tabs,
        "kpis": kpis,
    }
