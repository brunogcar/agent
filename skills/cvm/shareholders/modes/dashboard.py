"""Mode: dashboard -- multi-tab shareholders dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:          Summary text section (company, data de referência,
                       % free float, total acionistas, PL total)
  - Top Shareholders:  table of top 5 named shareholders (Acionista,
                       % Total, Qtde Total, Controlador)
  - Free Float:        single-row table (% Free Float, Acionistas PF,
                       Acionistas PJ, Acionistas Inst.)
  - Equity Structure:  table of BPP 2.03.* components (Componente, Valor BRL)

This mode does NOT fetch new data -- it calls ``summary()`` (which in turn
calls shareholders() + free_float() + equity_structure()) and reshapes the
result into a multi-tab payload. The summary() call is wrapped in
try/except so a missing FRE/DFP database degrades the corresponding tab
to an empty table instead of crashing the whole dashboard.

The section-building helpers live in skills.cvm.shareholders.report (so
they can be reused by other modes / tests). This module is the
orchestrator: gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.shareholders._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.shareholders._registry import register_mode
from skills.cvm.shareholders.modes.summary import summary
from skills.cvm.shareholders.report import (
    build_overview_kpis,
    build_overview_section,
    build_top_shareholders_section,
    build_free_float_section,
    build_equity_section,
    build_shareholder_doughnut,
    build_equity_structure_bar,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab shareholders dashboard (thin composition of summary()). "
        "Tabs: Overview (Summary text + 3 top-level KPI cards: % Free "
        "Float, Total Acionistas, PL Total), Top Shareholders (table: "
        "Acionista, % Total, Qtde Total, Controlador), Free Float (table: "
        "% Free Float, Acionistas PF/PJ/Inst.), Equity Structure (table: "
        "Componente, Valor BRL). Optimized for the report tool's dashboard "
        "action."
    ),
    params={
        "company": "str. B3 ticker (PETR4), name, or CNPJ. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="shareholders", mode="dashboard", '
        'params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """Multi-tab shareholders dashboard (thin composition of summary()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:          Summary text section
      - Top Shareholders:  table of top 5 named shareholders
      - Free Float:        single-row table of free float metrics
      - Equity Structure:  table of BPP 2.03.* components

    This mode does NOT fetch new data -- it calls ``summary()`` (which
    internally calls shareholders() + free_float() + equity_structure())
    and reshapes the result. The summary() call is wrapped in try/except
    so a partial failure still renders a usable dashboard with empty
    tabs.

    Args:
        company: B3 ticker (PETR4), name fragment, or CNPJ. Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no company), returns
        ``{"status": "error", "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    # ── Gather underlying data: summary() (best-effort over FRE + DFP) ──────
    # Defensive: wrap in try/except so a partial failure (e.g. FRE not synced,
    # company not in bridge) still renders a usable dashboard. When summary()
    # returns an error payload, each tab is built from the empty sections
    # (Top Shareholders tab has 0 rows, Free Float tab has 1 row of None
    # values, Equity Structure tab has 0 rows, all KPIs render as '—').
    print(f"[shareholders] Starting shareholders dashboard for "
          f"company='{company}'...", flush=True)
    print(f"[shareholders] Fetching summary data (shareholders + free float "
          f"+ equity)...", flush=True)
    summary_payload: dict = {}
    try:
        summary_payload = summary(company=company)
    except Exception as e:
        summary_payload = {"status": "error", "error": str(e)}

    # Pull out counts for the progress log.
    sh_section = ((summary_payload.get("sections") or {}).get("shareholders")
                  if isinstance(summary_payload, dict) else None) or {}
    eq_section = ((summary_payload.get("sections") or {}).get("equity")
                  if isinstance(summary_payload, dict) else None) or {}
    top_count = len(sh_section.get("top") or []) if isinstance(sh_section, dict) else 0
    eq_components = (eq_section.get("components")
                     if isinstance(eq_section, dict) else None) or {}
    eq_count = len(eq_components) if isinstance(eq_components, dict) else 0
    print(f"[shareholders] Data fetched: {top_count} top shareholders, "
          f"{eq_count} equity components.", flush=True)

    # ── Top-level KPI cards (% Free Float, Total Acionistas, PL Total) ─────
    print(f"[shareholders] Building KPI cards + tab sections...", flush=True)
    kpis = build_overview_kpis(summary_payload)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ─
    overview_sections = [build_overview_section(summary_payload)]

    # ── Tab 2: Top Shareholders -- top 5 named shareholders table + doughnut
    top_shareholders_sections = [build_top_shareholders_section(summary_payload)]
    top_list = (sh_section.get("top") or []) if isinstance(sh_section, dict) else []
    shareholder_doughnut = build_shareholder_doughnut(top_list)
    if shareholder_doughnut:
        top_shareholders_sections.append(shareholder_doughnut)

    # ── Tab 3: Free Float -- single-row table of free float metrics ──
    free_float_sections = [build_free_float_section(summary_payload)]

    # ── Tab 4: Equity Structure -- BPP 2.03.* components table + bar chart ──
    equity_sections = [build_equity_section(summary_payload)]
    equity_bar = build_equity_structure_bar(eq_section)
    if equity_bar:
        equity_sections.append(equity_bar)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",         "sections": overview_sections},
        {"name": "Top Shareholders", "sections": top_shareholders_sections},
        {"name": "Free Float",       "sections": free_float_sections},
        {"name": "Equity Structure", "sections": equity_sections},
    ]
    print(f"[shareholders] Done! {len(tabs)} tabs, {len(kpis)} KPIs, "
          f"{top_count} shareholders.", flush=True)

    # Prefer summary()'s company field when present (it's the resolved
    # company name from FRE/DFP); fall back to the input company string.
    company_out = summary_payload.get("company") or company

    return {
        "status": "ok",
        "company": company_out,
        "tabs": tabs,
        "kpis": kpis,
    }
