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

from skills.cvm.governance._registry import register_mode
from skills.cvm.governance.modes.practices import practices
from skills.cvm.governance.modes.score import score
from skills.cvm.governance.modes.by_chapter import by_chapter
from skills.cvm.governance.report import (
    build_overview_kpis,
    build_overview_section,
    build_practices_section,
    build_by_chapter_section,
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
    score_payload: dict = {}
    try:
        score_payload = score(company=company)
    except Exception as e:
        score_payload = {"status": "error", "error": str(e)}

    practices_payload: dict = {}
    try:
        practices_payload = practices(company=company)
    except Exception as e:
        practices_payload = {"status": "error", "error": str(e)}

    by_chapter_payload: dict = {}
    try:
        by_chapter_payload = by_chapter(company=company)
    except Exception as e:
        by_chapter_payload = {"status": "error", "error": str(e)}

    # ── Top-level KPI cards (Governance Score, Practices Count,
    #     Compliance Level) ──────────────────────────────────────────────────
    kpis = build_overview_kpis(score_payload, practices_payload)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ─
    overview_sections = [build_overview_section(score_payload, practices_payload)]

    # ── Tab 2: Practices -- full practices table ──
    practices_sections = [build_practices_section(practices_payload)]

    # ── Tab 3: By Chapter -- per-chapter adoption table ──
    by_chapter_sections = [build_by_chapter_section(by_chapter_payload)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",   "sections": overview_sections},
        {"name": "Practices",  "sections": practices_sections},
        {"name": "By Chapter", "sections": by_chapter_sections},
    ]

    # Prefer the score() result's company/cnpj/data_referencia when present
    # (matches what the Overview text section uses); fall back to the
    # practices() result, then the input company.
    company_out = (score_payload.get("company")
                   or practices_payload.get("company")
                   or company)

    return {
        "status": "ok",
        "company": company_out,
        "tabs": tabs,
        "kpis": kpis,
    }
