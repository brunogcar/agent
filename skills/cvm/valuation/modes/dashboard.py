"""Mode: dashboard -- multi-tab valuation dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview: KPI cards (P/L, P/VPA, EV/EBITDA, Div Yield, Market Cap, ROE)
    + price metadata + freshness
  - Multiples: all price ratios (P/L, P/VPA, P/EBIT, P/FCO, P/FCF,
    EV/EBITDA, EV/Sales, EV/FCF, PSR, Graham Number, P/Tangible Book)
  - Profitability: ROE, ROA, ROIC, Gross/Operating/Net/EBITDA/OCF/FCF
    margins, Effective Tax Rate
  - Liquidity & Leverage: Current/Quick/Cash Ratio, Working Capital,
    Debt/Equity, Net Debt/EBITDA, Cash Flow to Debt, Interest Coverage
  - Efficiency & Growth: Asset/Inventory/Receivables/Fixed Asset Turnover,
    CapEx/Revenue, Retention Ratio, Sustainable Growth

This mode does NOT fetch new data -- it calls `ratios()` and reshapes its
output into a multi-tab payload. If `ratios()` itself fails (e.g. price
unavailable), each tab degrades to all-None values; the dashboard payload
still builds successfully.

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
    build_multiples_section,
    build_profitability_section,
    build_liquidity_leverage_section,
    build_efficiency_growth_section,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab valuation dashboard (thin composition of ratios()). "
        "Tabs: Overview (6 KPI cards), Multiples (11 price ratios), "
        "Profitability (10 returns+margins), Liquidity & Leverage (8 ratios), "
        "Efficiency & Growth (7 ratios). Optimized for the report tool's "
        "dashboard action."
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
    """Multi-tab valuation dashboard (thin composition of ratios()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview: KPI cards (P/L, P/VPA, EV/EBITDA, Div Yield, Market Cap,
        ROE) + price metadata + freshness
      - Multiples: all price ratios + Graham Number + P/Tangible Book
      - Profitability: ROE/ROA/ROIC + 6 margins + Effective Tax Rate
      - Liquidity & Leverage: 4 liquidity + 4 leverage ratios
      - Efficiency & Growth: 5 efficiency + 2 growth ratios

    This mode does NOT fetch new data -- it calls `ratios()` and reshapes
    its output into a multi-tab payload. If `ratios()` itself fails (e.g.
    price unavailable), the outer status propagates and each tab degrades
    to all-None values; the dashboard payload still builds.

    Args:
        company: B3 ticker (PETR4). Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...]}``
        where each tab is ``{"name": str, "sections": [...]}``. The Overview
        tab additionally carries a ``kpis`` list. On empty company, returns
        ``{"status": "error", "error": "company is required"}``.
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
    ratios_dict = ratios_payload.get("ratios") if isinstance(ratios_payload, dict) else None

    # ── Tab 1: Overview -- KPI cards + price metadata + freshness ──────────
    kpis = build_overview_kpis(ratios_dict)
    overview_sections = build_overview_sections(ratios_dict, kpis)

    # ── Tabs 2-5: ratio grids ──────────────────────────────────────────────
    multiples_section = build_multiples_section(ratios_dict)
    profitability_section = build_profitability_section(ratios_dict)
    liquidity_leverage_section = build_liquidity_leverage_section(ratios_dict)
    efficiency_growth_section = build_efficiency_growth_section(ratios_dict)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    tabs = [
        {"name": "Overview",              "kpis": kpis, "sections": overview_sections},
        {"name": "Multiples",             "sections": [multiples_section]},
        {"name": "Profitability",         "sections": [profitability_section]},
        {"name": "Liquidity & Leverage",  "sections": [liquidity_leverage_section]},
        {"name": "Efficiency & Growth",   "sections": [efficiency_growth_section]},
    ]
    return {"status": "ok", "company": company, "tabs": tabs}
