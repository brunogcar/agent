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

from skills.cvm.dividends._registry import register_mode
from skills.cvm.dividends.modes.summary import summary
from skills.cvm.dividends.report import (
    build_overview_kpis,
    build_overview_section,
    build_history_section,
    build_annual_section,
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

    # ── Top-level KPI cards (Total Dividends Paid, Div Yield, Payout Ratio,
    #     Last Payment Date) ──
    kpis = build_overview_kpis(s, company=company)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ─
    overview_sections = [build_overview_section(s)]

    # ── Tab 2: History -- recent B3 dividend events table ──
    history_sections = [build_history_section(s)]

    # ── Tab 3: Annual -- DVA 7.08.04.* per fiscal year table ──
    annual_sections = [build_annual_section(s)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview", "sections": overview_sections},
        {"name": "History",  "sections": history_sections},
        {"name": "Annual",   "sections": annual_sections},
    ]
    return {
        "status": "ok",
        "company": s.get("company", company),
        "tabs": tabs,
        "kpis": kpis,
    }
