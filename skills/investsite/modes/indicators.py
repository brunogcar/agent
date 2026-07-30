"""Mode: indicators -- main indicators page (principais_indicadores.php).

Fetches the main investsite page and parses 10 sections of key-value data
(prices, DRE TTM/quarterly, returns/margins, balance sheet, cash flow,
experimental CAPEX/FCF).

Registered as "indicators" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] Moved verbatim from the former skills/investsite/investsite.py
monolith. fetcher.py + parsers.py are KEPT as separate modules (only the
mode logic was split out).
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.fetcher import fetch_page, url_indicators
from skills.investsite.parsers import parse_indicators


@register_mode(
    "indicators",
    description=(
        "Main page: 10 tables (dados básicos, preços relativos, DRE TTM/"
        "quarterly, retornos, balanço, fluxo de caixa, experimental)."
    ),
    include_in_all=True,
    params={
        "ticker": "str. B3 ticker (PETR4). Required.",
    },
    examples=[
        'skill(domain="investsite", mode="indicators", params=\'{"ticker":"PETR4"}\')',
    ],
)
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
