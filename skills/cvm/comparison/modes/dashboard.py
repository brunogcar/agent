"""Mode: dashboard -- multi-tab comparison dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:   KPI cards (cheapest P/L, best ROE, best Div Yield, cheapest
                EV/EBITDA) + Compared Tickers table (ticker + sector) +
                per-ticker errors (if any)
  - Valuation:  side-by-side valuation ratios table (all tickers × metrics)
  - Financials: side-by-side financial metrics table (latest annual)
  - Dividends:  side-by-side dividend metrics table
  - Growth:     QoQ + YoY + TTM ratios growth table

This mode does NOT fetch new data -- it calls ``side_by_side()`` and
``growth()`` and reshapes their outputs into a multi-tab payload. If
``side_by_side()`` itself fails (e.g. < 2 tickers), the dashboard
propagates the error dict instead of rendering empty tabs.

The section-building helpers live in skills.cvm.comparison.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.comparison._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.modes.side_by_side import side_by_side
from skills.cvm.comparison.modes.growth import growth
from skills.cvm.comparison.report import (
    build_overview_kpis,
    build_tickers_section,
    build_errors_section,
    build_valuation_section,
    build_financials_section,
    build_dividends_section,
    build_growth_section,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab comparison dashboard (thin composition of side_by_side() "
        "+ growth()). Tabs: Overview (4 KPI cards + tickers/sectors table), "
        "Valuation (side-by-side ratios), Financials (side-by-side metrics), "
        "Dividends (side-by-side dividend metrics), Growth (QoQ + YoY + TTM). "
        "Optimized for the report tool's dashboard action."
    ),
    params={
        "tickers":     "list[str]. B3 tickers, e.g. [\"PETR4\",\"VALE3\"]. Required (min 2).",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="dashboard", params=\'{"tickers":["PETR4","VALE3","ITUB4"]}\')',
    ],
)
def dashboard(tickers: list = None, consolidado: int = 1) -> dict:
    """Multi-tab comparison dashboard (thin composition of side_by_side() + growth()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:   KPI cards (cheapest P/L, best ROE, best Div Yield,
                    cheapest EV/EBITDA) + Compared Tickers table (with
                    sectors) + per-ticker errors (if any)
      - Valuation:  side-by-side valuation ratios table (all tickers × metrics)
      - Financials: side-by-side financial metrics table (latest annual)
      - Dividends:  side-by-side dividend metrics table
      - Growth:     QoQ + YoY + TTM ratios growth table

    This mode does NOT fetch new data -- it calls ``side_by_side()`` and
    ``growth()`` and reshapes their outputs into a multi-tab payload. If
    ``side_by_side()`` itself fails (e.g. < 2 tickers), the dashboard
    propagates the error dict instead of rendering empty tabs.

    Args:
        tickers: List of B3 tickers, e.g. ["PETR4","VALE3"]. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "tickers": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no tickers / < 2 tickers), returns the
        ``side_by_side()`` error dict verbatim.
    """
    # ── Gather underlying data (side_by_side + growth, wrapped defensively) ──
    try:
        sbs = side_by_side(tickers=tickers, consolidado=consolidado)
    except Exception as e:
        return {"status": "error",
                "sub_domain": "comparison", "mode": "dashboard",
                "error": str(e)}

    # Propagate validation errors (no tickers / < 2 tickers) as-is rather
    # than rendering empty tabs.
    if sbs.get("status") != "ok":
        return sbs

    # Growth mode is best-effort — if it fails for all tickers, the dashboard
    # still renders the other 4 tabs.
    try:
        growth_result = growth(tickers=tickers, consolidado=consolidado)
    except Exception:
        growth_result = {"status": "error", "sections": []}

    # ── Top-level KPI cards (leader per metric across all compared tickers) ──
    kpis = build_overview_kpis(sbs)

    # ── Tab 1: Overview -- KPI cards + tickers/sectors + per-ticker errors ─
    overview_sections = [build_tickers_section(sbs)]
    errors_section = build_errors_section(sbs)
    if errors_section is not None:
        overview_sections.append(errors_section)

    # ── Tab 2: Valuation -- side-by-side valuation ratios ──────────────────
    valuation_sections = [build_valuation_section(sbs)]

    # ── Tab 3: Financials -- side-by-side financial metrics ────────────────
    financials_sections = [build_financials_section(sbs)]

    # ── Tab 4: Dividends -- side-by-side dividend metrics ──────────────────
    dividends_sections = [build_dividends_section(sbs)]

    # ── Tab 5: Growth -- QoQ + YoY + TTM ratios ────────────────────────────
    growth_sections = [build_growth_section(growth_result)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",    "sections": overview_sections},
        {"name": "Valuation",   "sections": valuation_sections},
        {"name": "Financials",  "sections": financials_sections},
        {"name": "Dividends",   "sections": dividends_sections},
        {"name": "Growth",      "sections": growth_sections},
    ]
    return {
        "status": "ok",
        "tickers": sbs.get("tickers") or [],
        "tabs": tabs,
        "kpis": kpis,
    }
