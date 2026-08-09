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
from datetime import datetime as _dt

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
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
    _t0 = _dt.now()
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
    kpis = build_overview_kpis(summary_payload)

    # ── Build company header + price chart (v3 dashboard pattern) ──
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

    # [v5] One-line section timers (ratios pattern): 4 sections.
    _SEC_TOTAL = 4
    _sec_count = 0
    _sec_t0 = _dt.now()

    # ── Section 1/4: Overview ──────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info",
                                   "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    overview_sections.append(build_overview_section(summary_payload))
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/4: Top Shareholders ──────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    top_shareholders_sections = [build_top_shareholders_section(summary_payload)]
    top_list = (sh_section.get("top") or []) if isinstance(sh_section, dict) else []
    shareholder_doughnut = build_shareholder_doughnut(top_list)
    if shareholder_doughnut:
        top_shareholders_sections.append(shareholder_doughnut)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Top Shareholders ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/4: Free Float ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    free_float_sections = [build_free_float_section(summary_payload)]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Free Float ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 4/4: Equity Structure ──────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    equity_sections = [build_equity_section(summary_payload)]
    equity_bar = build_equity_structure_bar(eq_section)
    if equity_bar:
        equity_sections.append(equity_bar)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Equity Structure ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Acionistas / Estrutura.
    tabs = [
        {"name": "Overview",         "group": "Resumo",    "sections": overview_sections},
        {"name": "Top Shareholders", "group": "Acionistas","sections": top_shareholders_sections},
        {"name": "Free Float",       "group": "Acionistas","sections": free_float_sections},
        {"name": "Equity Structure", "group": "Estrutura", "sections": equity_sections},
    ]
    _total = (_dt.now() - _t0).total_seconds()
    print(f"[shareholders] Done! {len(tabs)} tabs, {len(kpis)} KPIs, "
          f"{top_count} shareholders in {_total:.1f}s.", flush=True)

    # Prefer summary()'s company field when present (it's the resolved
    # company name from FRE/DFP); fall back to the input company string.
    company_out = summary_payload.get("company") or company

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
