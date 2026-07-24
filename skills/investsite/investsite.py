"""skills/investsite/investsite.py -- Mode dispatch for investsite skill.

4 modes:
  indicators (default) — main page: 10 tables (basic data, prices, DRE, returns, balance, cashflow, experimental)
  statements          — full financial statement (BPA/BPP/DRE/DFC/DVA/shares) with % total columns
  events              — periodic info by category with CVM PDF links
  summary             — combined: key indicators + latest events

All data is fetched live from investsite.com.br. No local DB.
"""

from __future__ import annotations

from typing import Any

from skills.investsite.fetcher import (
    fetch_page, url_indicators, url_statement, url_events,
)
from skills.investsite.parsers import (
    parse_indicators, parse_statement, parse_events, EVENT_CATEGORIES,
)


# ── Mode: indicators (default) ───────────────────────────────────────────────

def indicators(ticker: str = "") -> dict:
    """Fetch the main indicators page (principais_indicadores.php).

    Returns 10 sections of data:
      - dados_basicos (company info)
      - precos_relativos (P/L, P/VPA, Market Cap, EV, Dividend Yield, etc.)
      - dre_ttm (Receita, EBIT, EBITDA, Lucro Líquido — trailing 12 months)
      - dre_quarterly (same — last quarter)
      - preco_volume (price/volume behavior)
      - retornos_margens (ROE, ROA, ROIC, margins, leverage, Dívida Líq/EBITDA)
      - balanco_patrimonial (Caixa, Ativo, Dívida, PL, VPA, share counts)
      - fluxo_caixa_ttm (FCO, FCI, FCF — trailing 12 months)
      - fluxo_caixa_quarterly (same — last quarter)
      - experimental (CAPEX + FCF — 3M and 12M)
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required (e.g., PETR4)"}

    ticker = ticker.strip().upper()

    try:
        html = fetch_page("principais_indicadores.php", {"cod_negociacao": ticker})
    except ConnectionError as e:
        return {"status": "error", "error": str(e)}

    result = parse_indicators(html)
    result["ticker"] = ticker
    result["source"] = url_indicators(ticker)
    return result


# ── Mode: statements ─────────────────────────────────────────────────────────

def statements(ticker: str = "", statement: str = "DRE") -> dict:
    """Fetch a full financial statement page.

    Args:
        ticker: B3 ticker (PETR4).
        statement: One of: BPA, BPP, DRE, DFC, DVA, shares.

    Returns:
        Dict with account codes, descriptions, period values + % total columns.
        This is an alternative to data_sources/cvm/dfp — the added value is
        the % total computed columns.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    statement = statement.strip().upper()

    valid = ["BPA", "BPP", "DRE", "DFC", "DVA", "SHARES"]
    if statement not in valid:
        return {"status": "error",
                "error": f"Unknown statement '{statement}'. Available: {valid}"}

    try:
        url = url_statement(ticker, statement)
        html = fetch_page(url)
    except (ConnectionError, ValueError) as e:
        return {"status": "error", "error": str(e)}

    result = parse_statement(html, statement)
    result["ticker"] = ticker
    result["source"] = url
    return result


# ── Mode: events ─────────────────────────────────────────────────────────────

def events(ticker: str = "", categoria: str = "", limit: int = 20) -> dict:
    """Fetch periodic info (IPE) by category from investsite.

    Returns events with direct CVM rad.cvm.gov.br PDF links.

    Args:
        ticker: B3 ticker (PETR4).
        categoria: Category filter. Empty = all. Available:
            Assembleia, Aviso aos Acionistas, Comunicado ao Mercado,
            Dados Econômico-Financeiros, Fato Relevante, Relatório Proventos,
            Reunião da Administração.
        limit: Max events to return. Default: 20.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()

    try:
        url = url_events(ticker, categoria)
        html = fetch_page(url)
    except ConnectionError as e:
        return {"status": "error", "error": str(e)}

    result = parse_events(html, categoria)
    result["ticker"] = ticker
    result["source"] = url

    if limit and result.get("events"):
        result["events"] = result["events"][:limit]
        result["count"] = len(result["events"])

    return result


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(ticker: str = "") -> dict:
    """Combined: key indicators + latest events (Fato Relevante).

    Best-effort — if one section fails, returns what's available.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    result: dict[str, Any] = {"status": "ok", "ticker": ticker, "sections": {}}

    # 1. Key indicators
    try:
        ind = indicators(ticker=ticker)
        if ind.get("status") == "ok":
            sections = ind.get("sections", {})
            result["sections"]["precos_relativos"] = sections.get("precos_relativos", {})
            result["sections"]["retornos_margens"] = sections.get("retornos_margens", {})
            result["sections"]["balanco_patrimonial"] = sections.get("balanco_patrimonial", {})
            result["sections"]["dre_ttm"] = sections.get("dre_ttm", {})
        else:
            result["sections"]["indicators"] = {"status": ind.get("status"),
                                                "error": ind.get("error", "")}
    except Exception as e:
        result["sections"]["indicators"] = {"status": "error", "error": str(e)}

    # 2. Latest Fato Relevante events
    try:
        evt = events(ticker=ticker, categoria="Fato Relevante", limit=10)
        if evt.get("status") == "ok":
            result["sections"]["latest_events"] = {
                "count": evt.get("count", 0),
                "events": evt.get("events", []),
            }
        else:
            result["sections"]["latest_events"] = {"status": evt.get("status"),
                                                    "error": evt.get("error", "")}
    except Exception as e:
        result["sections"]["latest_events"] = {"status": "error", "error": str(e)}

    return result


# ── Mode: listing (available categories) ─────────────────────────────────────

def listing(ticker: str = "") -> dict:
    """List available event categories for a ticker."""
    return {
        "status": "ok",
        "ticker": ticker.strip().upper() if ticker else "",
        "categories": EVENT_CATEGORIES,
        "note": "Use mode='events' with categoria param to fetch a specific category.",
    }
