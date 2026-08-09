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
from datetime import datetime as _dt

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
    _t0 = _dt.now()

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
    company_header = build_company_header(indicators_payload)
    kpis = build_overview_kpis(indicators_payload)

    # [v5] One-line section timers (ratios pattern): 12 sections.
    _SEC_TOTAL = 12
    _sec_count = 0
    _sec_t0 = _dt.now()

    # RESUMO: Overview
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_sections = build_overview_sections(indicators_payload)
    if company_header.get("name"):
        overview_sections.insert(0, {"type": "company_info", "company_header": company_header})
    multiples_chart = build_multiples_chart(indicators_payload)
    if multiples_chart:
        overview_sections.append(multiples_chart)
    returns_chart = build_returns_margins_chart(indicators_payload)
    if returns_chart:
        overview_sections.append(returns_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # INDICADORES: Preços Relativos
    _sec_count += 1
    _s_t0 = _dt.now()
    from skills.investsite.report import _build_split_tables
    precos_sections = []
    if indicators_payload.get("status") == "ok":
        precos = indicators_payload.get("sections", {}).get("precos_relativos", {}) or {}
        precos_sections = _build_split_tables(precos, "Preços Relativos")
    if multiples_chart:
        precos_sections.append(multiples_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Preços Relativos ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # INDICADORES: Retornos e Margens
    _sec_count += 1
    _s_t0 = _dt.now()
    retornos_sections = []
    if indicators_payload.get("status") == "ok":
        retornos = indicators_payload.get("sections", {}).get("retornos_margens", {}) or {}
        retornos_sections = _build_split_tables(retornos, "Retornos e Margens")
    if returns_chart:
        retornos_sections.append(returns_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Retornos e Margens ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # INDICADORES: Balanço Patrimonial (now returns list)
    _sec_count += 1
    _s_t0 = _dt.now()
    balanco_sections = build_balanco_section(indicators_payload)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Balanço Patrimonial ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # INDICADORES: Experimental (now returns list)
    _sec_count += 1
    _s_t0 = _dt.now()
    experimental_sections = build_experimental_section(indicators_payload)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} CAPEX e FCF ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # DEMONSTRAÇÕES: Balanço (BPA + BPP subtabs) — FIRST in group
    _sec_count += 1
    _s_t0 = _dt.now()
    bpa_section = build_statement_section(bpa_result, "Balanço Patrimonial Ativo")
    bpp_section = build_statement_section(bpp_result, "Balanço Patrimonial Passivo")
    balanco_full_sections = [{
        "type": "subtabs",
        "tabs": [
            {"name": "BPA", "sections": [bpa_section]},
            {"name": "BPP", "sections": [bpp_section]},
        ],
    }]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Balanço (BPA+BPP) ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # DEMONSTRAÇÕES: DRE
    _sec_count += 1
    _s_t0 = _dt.now()
    dre_sections = build_dre_sections(indicators_payload)
    dre_sections.append(build_statement_section(dre_full_result, "DRE Completo"))
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DRE ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # DEMONSTRAÇÕES: DFC
    _sec_count += 1
    _s_t0 = _dt.now()
    dfc_sections = build_dfc_sections(indicators_payload)
    dfc_sections.append(build_statement_section(dfc_full_result, "DFC Completo"))
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DFC ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # DEMONSTRAÇÕES: DVA
    _sec_count += 1
    _s_t0 = _dt.now()
    dva_section = build_statement_section(dva_result, "Demonstração do Valor Adicionado")
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} DVA ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # CORPORATIVO: Eventos
    _sec_count += 1
    _s_t0 = _dt.now()
    events_section = build_events_section(events_payload)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Eventos ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # CORPORATIVO: Quantidade de Ações
    _sec_count += 1
    _s_t0 = _dt.now()
    shares_sections = build_shares_sections(shares_html)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Quantidade de Ações ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # Freshness footer
    freshness_footer = "Dados de: investsite.com.br (cache 1h)"

    # Assemble tabs — Balanço first in Demonstrações
    tabs = [
        {"name": "Overview",              "group": "Resumo",          "sections": overview_sections},
        {"name": "Preços Relativos",      "group": "Análise",     "sections": precos_sections},
        {"name": "Retornos e Margens",    "group": "Análise",     "sections": retornos_sections},
        {"name": "Balanço Patrimonial",   "group": "Análise",     "sections": balanco_sections},
        {"name": "CAPEX e FCF",          "group": "Análise",     "sections": experimental_sections},
        {"name": "Balanço",               "group": "Demonstrações",   "sections": balanco_full_sections},
        {"name": "DRE",                   "group": "Demonstrações",   "sections": dre_sections},
        {"name": "DFC",                   "group": "Demonstrações",   "sections": dfc_sections},
        {"name": "DVA",                   "group": "Demonstrações",   "sections": [dva_section]},
        {"name": "Eventos",               "group": "Corporativo",     "sections": [events_section]},
        {"name": "Quantidade de Ações",   "group": "Corporativo",     "sections": shares_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[investsite] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {
        "status": "ok",
        "company": ticker,
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
