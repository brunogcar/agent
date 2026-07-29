"""Mode: dashboard -- multi-tab financial dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview: KPI cards (Receita, EBITDA, Lucro Líquido, Margem EBITDA,
    ROE, Dívida Líquida/EBITDA) + freshness metadata
  - DRE: Income statement (latest annual + 4-quarter trend)
  - Balanço: Balance sheet (Ativo + Passivo from latest annual)
  - DFC: Cash flow statement (latest annual + 4-quarter trend)
  - Ratios: Categorized ratio grid (profitability, liquidity, leverage,
    efficiency, growth, tax) via `compute_all_ratios()`

This mode does NOT fetch new data — it calls `annual()`, `quarterly()`,
and `compute_all_ratios()` and reshapes their output into a multi-tab
payload. Each sub-call is independently try/except-wrapped so a missing
DB degrades the corresponding tab to an error payload instead of
crashing the whole dashboard.

The section-building helpers live in skills.cvm.financials.report (so
they can be reused by other modes / tests). This module is the
orchestrator: gather data → call report.* builders → assemble tabs.

Registered as "dashboard" in skills.cvm.financials._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from datetime import date

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.modes.annual import annual
from skills.cvm.financials.modes.quarterly import quarterly
from skills.cvm.financials.report import (
    annual_metric,
    annual_ratio,
    build_overview_kpis,
    build_overview_sections,
    build_dre_sections,
    build_balanco_section,
    build_dfc_sections,
    build_ratios_section,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab financial dashboard (thin composition of annual() + "
        "quarterly() + compute_all_ratios()). Tabs: Overview (KPI cards), "
        "DRE, Balanço, DFC, Ratios. Optimized for the report tool's "
        "dashboard action."
    ),
    params={
        "company":     "str. Required.",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dashboard", params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "", consolidado: int = 1) -> dict:
    """Multi-tab financial dashboard (thin composition of existing modes).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview: KPI cards (Receita, EBITDA, Lucro Líquido, Margem EBITDA,
        ROE, Dívida Líquida/EBITDA) + freshness metadata
      - DRE: Income statement (latest annual + 4-quarter trend)
      - Balanço: Balance sheet (Ativo + Passivo from latest annual)
      - DFC: Cash flow statement (latest annual + 4-quarter trend)
      - Ratios: Categorized ratio grid (profitability, liquidity, leverage,
        efficiency, growth, tax) via `compute_all_ratios()`

    This mode does NOT fetch new data — it calls `annual()`, `quarterly()`,
    and `compute_all_ratios()` and reshapes their output into a multi-tab
    payload. Each sub-call is independently try/except-wrapped so a missing
    DB degrades the corresponding tab to an error payload instead of
    crashing the whole dashboard.

    Args:
        company: Ticker, name, or CNPJ. Required.
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...]}``
        where each tab is ``{"name": str, "sections": [...]}``. The Overview
        tab additionally carries a ``kpis`` list. On empty company, returns
        ``{"status": "error", "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    # ── Gather underlying data (each call wrapped independently) ────────────
    annual_payload: dict = {}
    try:
        annual_payload = annual(company=company, periods=1, consolidado=consolidado)
    except Exception as e:
        annual_payload = {"status": "error", "error": str(e)}

    quarterly_payload: dict = {}
    try:
        quarterly_payload = quarterly(company=company, periods=4, consolidado=consolidado)
    except Exception as e:
        quarterly_payload = {"status": "error", "error": str(e)}

    # Latest annual period (if available) — drives the KPI cards + DRE/Ativo/DFC tabs
    latest_annual_period: dict | None = None
    if annual_payload.get("status") == "ok" and annual_payload.get("periods"):
        latest_annual_period = annual_payload["periods"][0]

    # Quarterly trend (4 quarters newest-first or oldest-first — we'll reverse for display)
    quarterly_periods: list[dict] = []
    if quarterly_payload.get("status") == "ok" and quarterly_payload.get("periods"):
        quarterly_periods = quarterly_payload["periods"]

    # Current ratios via the calculations registry (same filter as summary())
    today = date.today().isoformat()
    ratios_payload: dict = {"date": today}
    try:
        from skills.cvm.calculations._registry import (
            compute_all_ratios, METRICS, list_metrics_by_category,
        )

        all_ratios = compute_all_ratios(
            company,
            today,
            categories=["profitability", "liquidity", "leverage",
                        "efficiency", "growth", "tax"],
            exclude=["lpa", "vpa", "dpa", "rps"],  # per-share metrics belong in valuation
        )
        ratios_payload.update(all_ratios)
    except Exception as e:
        ratios_payload["error"] = str(e)

    # ── Tab 1: Overview — KPI cards + freshness ────────────────────────────
    # Pull ROE + Dívida Líquida/EBITDA from the ratios registry (point-in-time
    # at today), falling back to the annual period's ratios when the registry
    # value is None (e.g. cotahist missing in test env).
    roe_val = ratios_payload.get("roe")
    if roe_val is None:
        roe_val = annual_ratio(latest_annual_period, "roe")
    net_debt_ebitda_val = ratios_payload.get("net_debt_ebitda")

    kpis = build_overview_kpis(latest_annual_period, roe_val, net_debt_ebitda_val)
    overview_sections = build_overview_sections(
        latest_annual_period, quarterly_periods)

    # ── Tab 2-5: DRE / Balanco / DFC / Ratios ─────────────────────────────
    dre_sections = build_dre_sections(latest_annual_period, quarterly_periods)
    balanco_section = build_balanco_section(latest_annual_period)
    dfc_sections = build_dfc_sections(latest_annual_period, quarterly_periods)
    ratios_section = build_ratios_section(today, ratios_payload)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview", "sections": overview_sections},
        {"name": "DRE",      "sections": dre_sections},
        {"name": "Balanco",  "sections": [balanco_section]},
        {"name": "DFC",      "sections": dfc_sections},
        {"name": "Ratios",   "sections": [ratios_section]},
    ]
    return {"status": "ok", "company": company, "tabs": tabs, "kpis": kpis}
