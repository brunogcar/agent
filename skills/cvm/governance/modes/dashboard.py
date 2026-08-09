"""Mode: dashboard -- multi-tab governance dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:   KPI cards (Governance Score, Practices Count, Compliance
                Level) + Summary text section
  - Practices:  table of all governance practices (recommended vs adopted,
                with chapter + principle + explanation)
  - By Chapter: table of governance practices grouped by chapter with
                adoption counts + score %

This mode does NOT fetch new data -- it calls ``score()``, ``practices()``,
and ``by_chapter()`` and reshapes their output into a multi-tab payload.
Each sub-call is independently try/except-wrapped so a missing CGVN DB
degrades the corresponding tab to an error payload instead of crashing
the whole dashboard.

The section-building helpers live in skills.cvm.governance.report (so
they can be reused by other modes / tests). This module is the
orchestrator: gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.governance._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.governance._registry import register_mode
from skills.cvm.governance.modes.practices import practices
from skills.cvm.governance.modes.score import score
from skills.cvm.governance.modes.by_chapter import by_chapter
from skills.cvm.governance.report import (
    build_overview_kpis,
    build_overview_section,
    build_practices_section,
    build_by_chapter_section,
    build_by_chapter_chart,
    build_practices_doughnut,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab governance dashboard (thin composition of score() + "
        "practices() + by_chapter()). Tabs: Overview (3 KPI cards: "
        "Governance Score, Practices Count, Compliance Level + Summary "
        "text), Practices (full practices table), By Chapter (per-chapter "
        "adoption counts). Optimized for the report tool's dashboard action."
    ),
    params={
        "company": "str. Ticker, name, or CNPJ. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="governance", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """Multi-tab governance dashboard (thin composition of existing modes).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:   KPI cards (Governance Score, Practices Count, Compliance
                    Level) + a Summary text section
      - Practices:  table of all governance practices (recommended vs
                    adopted, with chapter + principle + explanation)
      - By Chapter: table of governance practices grouped by chapter with
                    adoption counts + score %

    This mode does NOT fetch new data -- it calls ``score()``,
    ``practices()``, and ``by_chapter()`` and reshapes their output into a
    multi-tab payload. Each sub-call is independently try/except-wrapped
    so a missing CGVN DB degrades the corresponding tab to an error
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
    # The dashboard degrades gracefully: if score()/practices()/by_chapter()
    # returns an error payload (e.g. not_synced, not_found), the corresponding
    # tab is built from the error payload (sections will be empty or show a
    # status row via the adapter's _error_table fallback).
    print(f"[governance] Starting governance dashboard for company='{company}'...",
          flush=True)
    _t0 = _dt.now()
    print(f"[governance] Fetching score data...", flush=True)
    score_payload: dict = {}
    try:
        score_payload = score(company=company)
    except Exception as e:
        score_payload = {"status": "error", "error": str(e)}

    print(f"[governance] Fetching practices data...", flush=True)
    practices_payload: dict = {}
    try:
        practices_payload = practices(company=company)
    except Exception as e:
        practices_payload = {"status": "error", "error": str(e)}

    print(f"[governance] Fetching by-chapter data...", flush=True)
    by_chapter_payload: dict = {}
    try:
        by_chapter_payload = by_chapter(company=company)
    except Exception as e:
        by_chapter_payload = {"status": "error", "error": str(e)}

    practices_count = (len(practices_payload.get("practices") or [])
                       if isinstance(practices_payload, dict) else 0)
    print(f"[governance] Data fetched: {practices_count} practices.",
          flush=True)

    # ── Top-level KPI cards (Governance Score, Practices Count,
    #     Compliance Level) ──────────────────────────────────────────────────
    kpis = build_overview_kpis(score_payload, practices_payload)

    # ── Build company header + price chart (v3 dashboard pattern) ──
    company_header = build_company_header(company)
    price_chart = build_price_chart(company)

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
    overview_sections.append(build_overview_section(score_payload, practices_payload))
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/3: Practices ─────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    practices_sections = [build_practices_section(practices_payload)]
    practices_doughnut = build_practices_doughnut(practices_payload)
    if practices_doughnut:
        practices_sections.append(practices_doughnut)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Practices ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/3: By Chapter ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    by_chapter_sections = [build_by_chapter_section(by_chapter_payload)]
    # [v3] Add a horizontal bar chart showing Score % by chapter.
    chapter_chart = build_by_chapter_chart(by_chapter_payload)
    if chapter_chart:
        by_chapter_sections.append(chapter_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} By Chapter ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Governança.
    tabs = [
        {"name": "Overview",   "group": "Resumo",     "sections": overview_sections},
        {"name": "Practices",  "group": "Governança", "sections": practices_sections},
        {"name": "By Chapter", "group": "Governança", "sections": by_chapter_sections},
    ]
    _total = (_dt.now() - _t0).total_seconds()
    print(f"[governance] Done! {len(tabs)} tabs, {len(kpis)} KPIs, "
          f"{practices_count} practices in {_total:.1f}s.", flush=True)

    # Prefer the score() result's company/cnpj/data_referencia when present
    # (matches what the Overview text section uses); fall back to the
    # practices() result, then the input company.
    company_out = (score_payload.get("company")
                   or practices_payload.get("company")
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
