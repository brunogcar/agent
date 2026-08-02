"""Mode: dashboard -- multi-tab investsite dashboard with sidebar groups.

[v2.1] 11 tabs in 4 sidebar groups:
  RESUMO:
    - Overview (company header + split tables + charts)
  INDICADORES:
    - Preços Relativos (split tables + bar chart)
    - Retornos e Margens (split tables + bar chart)
    - Balanço Patrimonial (split tables + chart)
    - Experimental (split table + chart)
  DEMONSTRAÇÕES:
    - Balanço (BPA + BPP subtabs — full statements, grouped by prefix)
    - DRE (TTM + Quarterly split tables + full statement + bar chart)
    - DFC (TTM + Quarterly split tables + full statement + bar chart)
    - DVA (full statement, grouped by prefix)
  CORPORATIVO:
    - Eventos (IPE filings table)
    - Quantidade de Ações (3 tables: total, treasury, outstanding)
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.modes.indicators import indicators
from skills.investsite.modes.events import events
from skills.investsite.modes.statements import statements
from skills.investsite.fetcher import fetch_page, url_statement
from skills.investsite.report import (
    build_company_header,
    build_overview_kpis,
    build_overview_sections,
    build_multiples_chart,
    build_returns_margins_chart,
    build_balanco_section,
    build_experimental_section,
    build_dre_sections,
    build_dfc_sections,
    build_statement_section,
    build_events_section,
    build_shares_sections,
    _cell, _tip, _fv, _fmt,
)


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


@register_mode(
    "dashboard",
    description=(
        "Multi-tab investsite dashboard with sidebar groups. 11 tabs in "
        "4 groups: Resumo (Overview), Indicadores (Preços Relativos, "
        "Retornos e Margens, Balanço, Experimental), Demonstrações "
        "(Balanço BPA+BPP, DRE, DFC, DVA), Corporativo (Eventos, Ações)."
    ),
    include_in_all=False,
    params={"ticker": "str. B3 ticker (PETR4). Required."},
    examples=[
        'skill(domain="investsite", mode="dashboard", params=\'{"ticker":"PETR4"}\')',
    ],
)
def dashboard(ticker: str = "") -> dict:
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    print(f"[investsite] Starting dashboard for {ticker}...", flush=True)

    # ── Fetch ─────────────────────────────────────────────────────────
    print(f"[investsite] Fetching indicators...", flush=True)
    indicators_payload = _safe_call(indicators, ticker=ticker)
    _n_sec = len(indicators_payload.get("sections", {})) if indicators_payload.get("status") == "ok" else 0
    print(f"[investsite] Indicators: {_n_sec} sections.", flush=True)

    print(f"[investsite] Fetching events...", flush=True)
    events_payload = _safe_call(events, ticker=ticker, categoria="", limit=20)
    _n_evt = len(events_payload.get("events", [])) if events_payload.get("status") == "ok" else 0
    print(f"[investsite] Events: {_n_evt} found.", flush=True)

    print(f"[investsite] Fetching statements...", flush=True)
    bpa_result = _safe_call(statements, ticker=ticker, statement="BPA")
    print(f"[investsite]   BPA: {'ok' if bpa_result.get('status') == 'ok' else 'error'}", flush=True)
    bpp_result = _safe_call(statements, ticker=ticker, statement="BPP")
    print(f"[investsite]   BPP: {'ok' if bpp_result.get('status') == 'ok' else 'error'}", flush=True)
    dre_full_result = _safe_call(statements, ticker=ticker, statement="DRE")
    print(f"[investsite]   DRE: {'ok' if dre_full_result.get('status') == 'ok' else 'error'}", flush=True)
    dfc_full_result = _safe_call(statements, ticker=ticker, statement="DFC")
    print(f"[investsite]   DFC: {'ok' if dfc_full_result.get('status') == 'ok' else 'error'}", flush=True)
    dva_result = _safe_call(statements, ticker=ticker, statement="DVA")
    print(f"[investsite]   DVA: {'ok' if dva_result.get('status') == 'ok' else 'error'}", flush=True)

    print(f"[investsite] Fetching shares...", flush=True)
    shares_html = ""
    try:
        shares_html = fetch_page(url_statement(ticker, "SHARES"))
        print(f"[investsite]   Shares: ok", flush=True)
    except Exception as e:
        print(f"[investsite]   Shares: error ({e})", flush=True)

    # ── Build sections ────────────────────────────────────────────────
    print(f"[investsite] Building dashboard sections...", flush=True)

    company_header = build_company_header(indicators_payload)
    kpis = build_overview_kpis(indicators_payload)

    # RESUMO: Overview
    print(f"[investsite]   Overview tab...", flush=True)
    overview_sections = build_overview_sections(indicators_payload)
    if company_header.get("name"):
        overview_sections.insert(0, {"type": "company_info", "company_header": company_header})
    multiples_chart = build_multiples_chart(indicators_payload)
    if multiples_chart:
        overview_sections.append(multiples_chart)
    returns_chart = build_returns_margins_chart(indicators_payload)
    if returns_chart:
        overview_sections.append(returns_chart)

    # INDICADORES: Preços Relativos
    print(f"[investsite]   Preços Relativos tab...", flush=True)
    from skills.investsite.report import _build_split_tables
    precos_sections = []
    if indicators_payload.get("status") == "ok":
        precos = indicators_payload.get("sections", {}).get("precos_relativos", {}) or {}
        precos_sections = _build_split_tables(precos, "Preços Relativos")
    if multiples_chart:
        precos_sections.append(multiples_chart)

    # INDICADORES: Retornos e Margens
    print(f"[investsite]   Retornos e Margens tab...", flush=True)
    retornos_sections = []
    if indicators_payload.get("status") == "ok":
        retornos = indicators_payload.get("sections", {}).get("retornos_margens", {}) or {}
        retornos_sections = _build_split_tables(retornos, "Retornos e Margens")
    if returns_chart:
        retornos_sections.append(returns_chart)

    # INDICADORES: Balanço Patrimonial (now returns list)
    print(f"[investsite]   Balanço tab...", flush=True)
    balanco_sections = build_balanco_section(indicators_payload)

    # INDICADORES: Experimental (now returns list)
    print(f"[investsite]   Experimental tab...", flush=True)
    experimental_sections = build_experimental_section(indicators_payload)

    # DEMONSTRAÇÕES: Balanço (BPA + BPP subtabs) — FIRST in group
    print(f"[investsite]   Balanço (BPA+BPP) tab...", flush=True)
    bpa_section = build_statement_section(bpa_result, "Balanço Patrimonial Ativo")
    bpp_section = build_statement_section(bpp_result, "Balanço Patrimonial Passivo")
    balanco_full_sections = [{
        "type": "subtabs",
        "tabs": [
            {"name": "BPA", "sections": [bpa_section]},
            {"name": "BPP", "sections": [bpp_section]},
        ],
    }]

    # DEMONSTRAÇÕES: DRE
    print(f"[investsite]   DRE tab...", flush=True)
    dre_sections = build_dre_sections(indicators_payload)
    dre_sections.append(build_statement_section(dre_full_result, "DRE Completo"))

    # DEMONSTRAÇÕES: DFC
    print(f"[investsite]   DFC tab...", flush=True)
    dfc_sections = build_dfc_sections(indicators_payload)
    dfc_sections.append(build_statement_section(dfc_full_result, "DFC Completo"))

    # DEMONSTRAÇÕES: DVA
    print(f"[investsite]   DVA tab...", flush=True)
    dva_section = build_statement_section(dva_result, "Demonstração do Valor Adicionado")

    # CORPORATIVO: Eventos
    print(f"[investsite]   Eventos tab...", flush=True)
    events_section = build_events_section(events_payload)

    # CORPORATIVO: Quantidade de Ações
    print(f"[investsite]   Ações tab...", flush=True)
    shares_sections = build_shares_sections(shares_html)

    # Freshness footer
    freshness_footer = "Dados de: investsite.com.br (cache 1h)"

    # Assemble tabs — Balanço first in Demonstrações
    tabs = [
        {"name": "Overview",              "group": "Resumo",          "sections": overview_sections},
        {"name": "Preços Relativos",      "group": "Indicadores",     "sections": precos_sections},
        {"name": "Retornos e Margens",    "group": "Indicadores",     "sections": retornos_sections},
        {"name": "Balanço Patrimonial",   "group": "Indicadores",     "sections": balanco_sections},
        {"name": "Experimental",          "group": "Indicadores",     "sections": experimental_sections},
        {"name": "Balanço",               "group": "Demonstrações",   "sections": balanco_full_sections},
        {"name": "DRE",                   "group": "Demonstrações",   "sections": dre_sections},
        {"name": "DFC",                   "group": "Demonstrações",   "sections": dfc_sections},
        {"name": "DVA",                   "group": "Demonstrações",   "sections": [dva_section]},
        {"name": "Eventos",               "group": "Corporativo",     "sections": [events_section]},
        {"name": "Quantidade de Ações",   "group": "Corporativo",     "sections": shares_sections},
    ]

    print(f"[investsite] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)
    return {
        "status": "ok",
        "company": ticker,
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
