"""Mode: dashboard -- 7-tab financial dashboard (thin composition mode).

[v1.12] Reorganized from 5 tabs to 7 tabs with sub-tabs + charts:

  1. Overview     — KPI cards (Receita, EBITDA, Lucro Líquido, ROE, ROIC,
                    Dív.Líq/EBITDA) + latest-annual summary table +
                    quarterly trend + freshness metadata
  2. Indicadores  — ALL ratios in one categorized ratio_grid (valuation,
                    profitability, liquidity, leverage, efficiency, growth,
                    tax) via compute_all_ratios()
  3. Crescimento  — 3M/1Y/5Y growth table (Receita, Lucro Bruto, Lucro
                    Líquido) + bar chart
  4. Balanço      — BPA + BPP as `type: "subtabs"` (2 sub-tabs)
  5. DRE          — latest annual accounts table + 5Y margin trend chart
  6. DFC          — latest annual accounts table + 5Y stacked bar chart
                    (FCO / FCI / FCF)
  7. DVA          — latest annual accounts table + doughnut chart of
                    wealth distribution

DESIGN
------
The dashboard mode does NOT fetch new data — it calls the standalone
statement modes (bpa, bpp, dre, dfc, dva) for statement tables, plus
annual() / quarterly() / compute_all_ratios() for the summary sections.
Each sub-call is independently try/except-wrapped so a missing DB
degrades the corresponding tab to an error payload instead of crashing
the whole dashboard.

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
    build_indicadores_section,
    build_crescimento_sections,
    build_balanco_section,
    build_dre_sections,
    build_dfc_sections,
    build_dva_sections,
    build_error_section,
)


def _safe_call(fn, *args, **kwargs):
    """Call a sub-mode and return its dict, or an error payload on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


@register_mode(
    "dashboard",
    description=(
        "Multi-tab financial dashboard (thin composition of annual() + "
        "quarterly() + compute_all_ratios() + 5 standalone statement "
        "modes). 7 tabs: Overview (KPI cards + summary), Indicadores "
        "(ratio_grid with all 55 metrics), Crescimento (3M/1Y/5Y growth "
        "+ bar chart), Balanço (BPA + BPP subtabs), DRE (table + margin "
        "trend chart), DFC (table + stacked bar chart), DVA (table + "
        "doughnut chart). Optimized for the report tool's dashboard action."
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
    """7-tab financial dashboard (thin composition of existing modes).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:

      1. Overview     — KPI cards + latest-annual summary table + quarterly
                        trend + freshness metadata
      2. Indicadores  — categorized ratio_grid (all 55 calculations metrics)
      3. Crescimento  — 3M/1Y/5Y growth table + bar chart
      4. Balanço      — BPA + BPP as `type: "subtabs"`
      5. DRE          — latest annual accounts table + margin trend chart
      6. DFC          — latest annual accounts table + stacked bar chart
      7. DVA          — latest annual accounts table + doughnut chart

    Each sub-call is independently try/except-wrapped so a missing DB
    degrades the corresponding tab to an error payload instead of
    crashing the whole dashboard.

    Args:
        company: Ticker, name, or CNPJ. Required.
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...], "kpis": [...]}``
        where each tab is ``{"name": str, "sections": [...]}``. On empty
        company, returns ``{"status": "error", "error": "company is required"}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[financials] Starting dashboard for {company}...", flush=True)

    # ── Gather underlying data (each call wrapped independently) ────────────
    print(f"[financials] Fetching annual data (5 periods)...", flush=True)
    annual_payload = _safe_call(annual, company=company, periods=5,
                                consolidado=consolidado)
    print(f"[financials] Fetching quarterly data (4 periods)...", flush=True)
    quarterly_payload = _safe_call(quarterly, company=company, periods=4,
                                   consolidado=consolidado)

    latest_annual_period: dict | None = None
    annual_periods: list[dict] = []
    if annual_payload.get("status") == "ok" and annual_payload.get("periods"):
        annual_periods = annual_payload["periods"]
        latest_annual_period = annual_periods[0]

    quarterly_periods: list[dict] = []
    if quarterly_payload.get("status") == "ok" and quarterly_payload.get("periods"):
        quarterly_periods = quarterly_payload["periods"]

    # Current ratios via the calculations registry (point-in-time at today).
    today = date.today().isoformat()
    ratios_payload: dict = {"date": today}
    print(f"[financials] Computing ratios (via compute_all_ratios)...", flush=True)
    try:
        from skills.cvm.calculations._registry import compute_all_ratios

        all_ratios = compute_all_ratios(
            company,
            today,
            categories=["profitability", "liquidity", "leverage",
                        "efficiency", "growth", "tax", "valuation"],
            exclude=["lpa", "vpa", "dpa", "rps"],  # per-share metrics belong in valuation
        )
        ratios_payload.update(all_ratios)
    except Exception as e:
        ratios_payload["error"] = str(e)

    # ── Standalone statement modes (each wrapped independently) ─────────────
    # We fetch the latest annual period for each statement. Failures degrade
    # the corresponding tab to an error section, not a crash.
    print(f"[financials] Fetching statement modes (BPA/BPP/DRE/DFC/DVA)...", flush=True)
    bpa_result = _safe_call(_call_bpa, company, consolidado)
    print(f"[financials]   Fetching BPA... done.", flush=True)
    bpp_result = _safe_call(_call_bpp, company, consolidado)
    print(f"[financials]   Fetching BPP... done.", flush=True)
    dre_result = _safe_call(_call_dre, company, consolidado)
    print(f"[financials]   Fetching DRE... done.", flush=True)
    dfc_result = _safe_call(_call_dfc, company, consolidado)
    print(f"[financials]   Fetching DFC... done.", flush=True)
    dva_result = _safe_call(_call_dva, company, consolidado)
    print(f"[financials]   Fetching DVA... done.", flush=True)

    # ── Tab 1: Overview ─────────────────────────────────────────────────────
    print(f"[financials] Building dashboard sections...", flush=True)
    # Pull ROE + ROIC + Net Debt/EBITDA from the ratios registry (point-in-time
    # at today), falling back to the annual period's ratios when the registry
    # value is None (e.g. cotahist missing in test env).
    roe_val = ratios_payload.get("roe")
    if roe_val is None:
        roe_val = annual_ratio(latest_annual_period, "roe")
    roic_val = ratios_payload.get("roic")
    if roic_val is None:
        roic_val = annual_ratio(latest_annual_period, "roic")
    net_debt_ebitda_val = ratios_payload.get("net_debt_ebitda")

    kpis = build_overview_kpis(latest_annual_period, roe_val, roic_val,
                               net_debt_ebitda_val)
    overview_sections = build_overview_sections(
        latest_annual_period, quarterly_periods, ratios_payload)

    # ── Tab 2: Indicadores ──────────────────────────────────────────────────
    indicadores_section = build_indicadores_section(today, ratios_payload)

    # ── Tab 3: Crescimento ──────────────────────────────────────────────────
    crescimento_sections = build_crescimento_sections(
        latest_annual_period, annual_periods)

    # ── Tab 4: Balanço (BPA + BPP subtabs) ──────────────────────────────────
    if bpa_result.get("status") == "ok" or bpp_result.get("status") == "ok":
        balanco_section = build_balanco_section(bpa_result, bpp_result)
    else:
        balanco_section = {
            "type": "text",
            "text": (
                "Balanço indisponível para esta empresa. "
                f"Detalhe BPA: {bpa_result.get('error', '—')}. "
                f"Detalhe BPP: {bpp_result.get('error', '—')}."
            ),
        }

    # ── Tab 5: DRE ──────────────────────────────────────────────────────────
    if dre_result.get("status") == "ok":
        dre_sections = build_dre_sections(
            dre_result, annual_periods, latest_annual_period)
    else:
        dre_sections = [build_error_section(
            "DRE", dre_result.get("error", "unknown"))]

    # ── Tab 6: DFC ──────────────────────────────────────────────────────────
    if dfc_result.get("status") == "ok":
        dfc_sections = build_dfc_sections(
            dfc_result, annual_periods, latest_annual_period)
    else:
        dfc_sections = [build_error_section(
            "DFC", dfc_result.get("error", "unknown"))]

    # ── Tab 7: DVA ──────────────────────────────────────────────────────────
    if dva_result.get("status") == "ok":
        dva_sections = build_dva_sections(dva_result)
    else:
        dva_sections = [build_error_section(
            "DVA", dva_result.get("error", "unknown"))]

    # ── Assemble the dashboard payload ──────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",     "sections": overview_sections},
        {"name": "Indicadores",  "sections": [indicadores_section]},
        {"name": "Crescimento",  "sections": crescimento_sections},
        {"name": "Balanço",      "sections": [balanco_section]},
        {"name": "DRE",          "sections": dre_sections},
        {"name": "DFC",          "sections": dfc_sections},
        {"name": "DVA",          "sections": dva_sections},
    ]
    print(f"[financials] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)
    return {"status": "ok", "company": company, "tabs": tabs, "kpis": kpis}


# ── Statement-mode call helpers ──────────────────────────────────────────────
# These exist so the dashboard module's try/except wraps a single function
# call per statement (cleaner than wrapping the import + call inline).

def _call_bpa(company: str, consolidado: int) -> dict:
    from skills.cvm.financials.modes.bpa import bpa
    return bpa(company=company, period="annual", consolidado=consolidado, periods=1)


def _call_bpp(company: str, consolidado: int) -> dict:
    from skills.cvm.financials.modes.bpp import bpp
    return bpp(company=company, period="annual", consolidado=consolidado, periods=1)


def _call_dre(company: str, consolidado: int) -> dict:
    from skills.cvm.financials.modes.dre import dre
    return dre(company=company, period="annual", consolidado=consolidado, periods=1)


def _call_dfc(company: str, consolidado: int) -> dict:
    from skills.cvm.financials.modes.dfc import dfc
    return dfc(company=company, period="annual", consolidado=consolidado, periods=1)


def _call_dva(company: str, consolidado: int) -> dict:
    from skills.cvm.financials.modes.dva import dva
    return dva(company=company, period="annual", consolidado=consolidado, periods=1)
