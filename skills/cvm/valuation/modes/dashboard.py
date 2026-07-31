"""Mode: dashboard -- 6-tab valuation dashboard (thin composition mode).

[v1.5] Reorganized from 5 tabs to 6 tabs with sub-tabs + charts + collapsibles:

  1. Overview              — KPI cards (P/L, P/VPA, EV/EBITDA, Div Yield,
                             Market Cap, ROE) + Key Metrics table + Price
                             Details collapsible
  2. Multiples             — Top-10 multiples table [Métrica, Valor,
                             Interpretação] + bar chart (P/L, P/VPA,
                             EV/EBITDA, PSR) + "Less Common Multiples"
                             collapsible (6 less-common metrics)
  3. Per-share             — Per-share values table [Métrica, Valor (R$),
                             Preço/Valor] + bar chart (per-share side-by-side)
  4. Profitability         — ratio_grid with 1 category (ROE/ROA/ROIC +
                             6 margins)
  5. Liquidity & Leverage  — ratio_grid with 2 categories (Liquidity +
                             Leverage) + "Detailed Leverage" collapsible
                             (DL/EBIT, DL/EBITDA, Gross D/E)
  6. Efficiency & Growth   — Efficiency table + Growth table (3M/1Y/5Y) +
                             bar chart (3M/1Y/5Y growth side-by-side for
                             Revenue/GP/NI — on ROADMAP until historical
                             engines are wired)

This mode does NOT fetch new data -- it calls ``ratios()`` ONCE and passes
the resulting ratios dict to every tab builder. If ``ratios()`` itself
fails (e.g. price unavailable), the outer status propagates and each tab
degrades to all-None values; the dashboard payload still builds
successfully.

Each tab builder is independently try/except-wrapped so a failure in one
tab (e.g. a builder raising an unexpected error) degrades to an error
section, not a crash of the whole dashboard.

The section-building helpers live in skills.cvm.valuation.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.valuation._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.valuation._registry import register_mode
from skills.cvm.valuation.modes.ratios import ratios
from skills.cvm.valuation.report import (
    build_overview_kpis,
    build_overview_sections,
    build_multiples_sections,
    build_per_share_sections,
    build_profitability_section,
    build_liquidity_leverage_sections,
    build_efficiency_growth_sections,
)


def _safe_build(fn, ratios_dict):
    """Call a section builder, returning an error-section list on failure.

    Each builder in report.py is supposed to tolerate None values + missing
    keys gracefully, but we wrap it defensively so an unexpected exception
    in one builder doesn't crash the whole dashboard. On failure, the tab
    degrades to a single text section with the error message.
    """
    try:
        sections = fn(ratios_dict)
        if not isinstance(sections, list):
            # Single-section builders return a dict — wrap in a list.
            if isinstance(sections, dict):
                return [sections]
            return [{"type": "text",
                     "text": "Builder returned unexpected type: "
                             f"{type(sections).__name__}"}]
        return sections
    except Exception as e:
        return [{
            "type": "text",
            "text": f"Section unavailable: {e}",
        }]


@register_mode(
    "dashboard",
    description=(
        "Multi-tab valuation dashboard (thin composition of ratios()). "
        "6 tabs: Overview (KPI cards + Key Metrics + Price Details "
        "collapsible), Multiples (top-10 table + bar chart + less-common "
        "collapsible), Per-share (table + bar chart), Profitability "
        "(ratio_grid), Liquidity & Leverage (ratio_grid + Detailed "
        "Leverage collapsible), Efficiency & Growth (table + 3M/1Y/5Y "
        "growth chart). Calls ratios() once + passes the result to every "
        "tab builder. Optimized for the report tool's dashboard action."
    ),
    params={
        "company": "str. B3 ticker (PETR4). Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="valuation", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """6-tab valuation dashboard (thin composition of ratios()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      1. Overview              — KPI cards + Key Metrics + Price Details
      2. Multiples             — Top-10 table + chart + collapsible
      3. Per-share             — Per-share table + chart
      4. Profitability         — ratio_grid (1 category)
      5. Liquidity & Leverage  — ratio_grid (2 categories) + collapsible
      6. Efficiency & Growth   — Efficiency table + Growth table + chart

    This mode does NOT fetch new data -- it calls ``ratios()`` ONCE and
    passes the ratios dict to every tab builder. If ``ratios()`` itself
    fails (e.g. price unavailable), the outer status propagates and each
    tab degrades to all-None values; the dashboard payload still builds.

    Each tab builder is independently try/except-wrapped so an unexpected
    failure in one builder degrades to an error section in that tab, not
    a crash of the whole dashboard.

    Args:
        company: B3 ticker (PETR4). Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections":
        [...]}``. The Overview tab additionally carries a ``kpis`` list at
        the top level. On empty company, returns ``{"status": "error",
        "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    # ── Gather underlying data (ratios() wrapped defensively) ──────────────
    # ratios() can return status="ok" with ratios={"status": "error", ...}
    # when the price source fails. In that case we still build the dashboard
    # payload, but every ratio value will be None.
    try:
        ratios_payload = ratios(company=company)
    except Exception as e:
        ratios_payload = {"status": "error", "error": str(e)}

    # The actual ratios dict lives under ratios_payload["ratios"]. When
    # ratios() short-circuited (no company / invalid ticker), this key
    # may be missing or be a {"status": "error", ...} dict -- the report.*
    # builders handle both via _safe_get().
    ratios_dict = (
        ratios_payload.get("ratios")
        if isinstance(ratios_payload, dict) else None
    )

    # ── Tab 1: Overview -- KPI cards (top-level) + Key Metrics + Price Details ──
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    kpis = build_overview_kpis(ratios_dict)
    overview_sections = _safe_build(build_overview_sections, ratios_dict)

    # ── Tab 2: Multiples -- top-10 table + chart + less-common collapsible ──
    multiples_sections = _safe_build(build_multiples_sections, ratios_dict)

    # ── Tab 3: Per-share -- table + bar chart ──
    per_share_sections = _safe_build(build_per_share_sections, ratios_dict)

    # ── Tab 4: Profitability -- ratio_grid ──
    profitability_sections = _safe_build(
        build_profitability_section, ratios_dict)

    # ── Tab 5: Liquidity & Leverage -- ratio_grid + collapsible ──
    liquidity_leverage_sections = _safe_build(
        build_liquidity_leverage_sections, ratios_dict)

    # ── Tab 6: Efficiency & Growth -- table + chart ──
    efficiency_growth_sections = _safe_build(
        build_efficiency_growth_sections, ratios_dict)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    tabs = [
        {"name": "Overview",              "sections": overview_sections},
        {"name": "Multiples",             "sections": multiples_sections},
        {"name": "Per-share",             "sections": per_share_sections},
        {"name": "Profitability",         "sections": profitability_sections},
        {"name": "Liquidity & Leverage",  "sections": liquidity_leverage_sections},
        {"name": "Efficiency & Growth",   "sections": efficiency_growth_sections},
    ]
    return {"status": "ok", "company": company, "tabs": tabs, "kpis": kpis}
