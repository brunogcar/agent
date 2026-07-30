"""Mode: dashboard -- multi-tab investsite dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:        KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield)
                     + Summary text section (ticker, company, headline metrics)
  - Key Indicators:  2-column table flattening precos_relativos +
                     retornos_margens from indicators() (P/L, P/VPA, EV/EBITDA,
                     Dividend Yield, ROE, ROA, Margem EBITDA, Margem Líquida)
  - Latest Events:   4-column table (Data, Categoria, Descrição, Link) of the
                     10 most recent Fato Relevante events with direct CVM
                     rad.cvm.gov.br PDF links

This mode does NOT fetch new data beyond what indicators() + events() fetch
-- it calls them and reshapes their output into a multi-tab payload. Each
sub-call is independently try/except-wrapped so a network/parse failure
degrades the corresponding tab to an empty/error payload instead of
crashing the whole dashboard.

The section-building helpers live in skills.investsite.report (so they can
be reused by other modes / tests). This module is the orchestrator: gather
data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] NEW — added as part of the modular split.
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.modes.indicators import indicators
from skills.investsite.modes.events import events
from skills.investsite.report import (
    build_overview_kpis,
    build_overview_section,
    build_key_indicators_section,
    build_latest_events_section,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab investsite dashboard (thin composition of indicators() + "
        "events()). Tabs: Overview (5 KPI cards: P/L, P/VPA, EV/EBITDA, ROE, "
        "Dividend Yield + Summary text), Key Indicators (valuation + "
        "returns/margins table), Latest Events (recent Fato Relevante with "
        "CVM PDF links). Optimized for the report tool's dashboard action."
    ),
    include_in_all=False,
    params={
        "ticker": "str. B3 ticker (PETR4). Required.",
    },
    examples=[
        'skill(domain="investsite", mode="dashboard", params=\'{"ticker":"PETR4"}\')',
    ],
)
def dashboard(ticker: str = "") -> dict:
    """Multi-tab investsite dashboard (thin composition of existing modes).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:        KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend
                         Yield) + a Summary text section (ticker, company,
                         headline metrics)
      - Key Indicators:  2-column [Indicador, Valor] table flattening
                         precos_relativos + retornos_margens
      - Latest Events:   4-column [Data, Categoria, Descrição, Link] table
                         of the 10 most recent Fato Relevante events with
                         direct CVM rad.cvm.gov.br PDF links

    This mode does NOT fetch new data beyond what indicators() + events()
    fetch — it calls them and reshapes their output into a multi-tab
    payload. Each sub-call is independently try/except-wrapped so a
    network/parse failure degrades the corresponding tab to an empty
    payload (table has 0 rows, KPIs render as "—") instead of crashing
    the whole dashboard.

    Args:
        ticker: B3 ticker (PETR4). Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no ticker), returns
        ``{"status": "error", "error": "ticker is required"}``.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    # ── Gather underlying data (each call wrapped independently) ────────────
    # The dashboard degrades gracefully: if indicators() or events() returns
    # an error payload (e.g. ConnectionError, parse failure), the
    # corresponding tab is built from the error payload (sections will be
    # empty or show a status row via the adapter's _error_table fallback).
    indicators_payload: dict = {}
    try:
        indicators_payload = indicators(ticker=ticker)
    except Exception as e:
        indicators_payload = {"status": "error", "error": str(e)}

    events_payload: dict = {}
    try:
        events_payload = events(
            ticker=ticker,
            categoria="Fato Relevante",
            limit=10,
        )
    except Exception as e:
        events_payload = {"status": "error", "error": str(e)}

    # ── Top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield) ───
    kpis = build_overview_kpis(indicators_payload)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ─
    overview_sections = [build_overview_section(indicators_payload)]

    # ── Tab 2: Key Indicators -- precos_relativos + retornos_margens table ──
    key_indicators_sections = [build_key_indicators_section(indicators_payload)]

    # ── Tab 3: Latest Events -- recent Fato Relevante table ──────────────────
    latest_events_sections = [build_latest_events_section(events_payload)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",        "sections": overview_sections},
        {"name": "Key Indicators",  "sections": key_indicators_sections},
        {"name": "Latest Events",   "sections": latest_events_sections},
    ]

    # Prefer the indicators() result's ticker (uppercased by indicators());
    # fall back to the events() result, then the input ticker.
    company_out = (indicators_payload.get("ticker")
                   or events_payload.get("ticker")
                   or ticker.strip().upper())

    return {
        "status": "ok",
        "company": company_out,
        "tabs": tabs,
        "kpis": kpis,
    }
