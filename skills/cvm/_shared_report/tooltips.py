"""skills/cvm/_shared_report/tooltips.py — Tooltip registry for indicators.

[v1.16.1] Extracted from skills/cvm/financials/report.py. Centralizes the
PT-BR formula/explanation strings for dashboard ratio_grid items.

The _get_tooltip() helper checks (in order):
  1. The local _METRIC_TOOLTIPS dict (curated, most detailed)
  2. MetricSpec.tooltip field (set at registration time in each metric file)
  3. Returns "" (no tooltip)

This means new metrics get tooltips for free if they set tooltip= at
registration, without needing to edit this file.
"""
from __future__ import annotations

from typing import Any


# Curated PT-BR tooltips (formula + brief explanation). Keep under ~120 chars.
_METRIC_TOOLTIPS = {
    # profitability
    "roe": "ROE = Lucro Líquido / Patrimônio Líquido. Rentabilidade do capital dos acionistas.",
    "roa": "ROA = Lucro Líquido / Ativo Total. Eficiência do uso dos ativos.",
    "roic": "ROIC = NOPAT / Capital Investido. Retorno sobre o capital aportado.",
    "gross_margin": "Margem Bruta = Lucro Bruto / Receita Líquida.",
    "operating_margin": "Margem Operacional = EBIT / Receita Líquida.",
    "net_margin": "Margem Líquida = Lucro Líquido / Receita Líquida.",
    "ebitda_margin": "Margem EBITDA = EBITDA / Receita Líquida.",
    "ocf_margin": "Margem FCO = Fluxo de Caixa Operacional / Receita Líquida.",
    "fcf_margin": "Margem FCF = Fluxo de Caixa Livre / Receita Líquida.",
    # liquidity
    "current_ratio": "Liquidez Corrente = Ativo Circulante / Passivo Circulante.",
    "quick_ratio": "Liquidez Seca = (Ativo Circulante - Estoques) / Passivo Circulante.",
    "cash_ratio": "Liquidez Imediata = Caixa / Passivo Circulante.",
    "working_capital": "Capital de Giro = Ativo Circulante - Passivo Circulante.",
    # leverage
    "debt_equity": "Dívida/PL = Dívida Bruta / Patrimônio Líquido.",
    "net_debt_ebitda": "Dív. Líq/EBITDA = (Dívida Bruta - Caixa) / EBITDA. Alavanca operacional.",
    "dl_ebit": "Dív. Líq/EBIT = (Dívida Bruta - Caixa) / EBIT.",
    "interest_coverage": "Cobertura de Juros = EBIT / Juros Líquidos Passivos.",
    "cash_flow_to_debt": "FCO/Dívida = Fluxo de Caixa Operacional / Dívida Bruta.",
    # efficiency
    "asset_turnover": "Giro do Ativo = Receita Líquida / Ativo Total.",
    "inventory_turnover": "Giro de Estoque = CMV / Estoque Médio.",
    "receivables_turnover": "Giro de Contas a Receber = Receita / Contas a Receber.",
    "fixed_asset_turnover": "Giro do Imobilizado = Receita / Imobilizado Líquido.",
    "capex_revenue": "Capex/Receita = Investimentos / Receita Líquida.",
    # growth
    "retention_ratio": "Taxa de Retenção = 1 - Payout. Parcela do lucro retida.",
    "sustainable_growth": "Crescimento Sustentável = ROE × Taxa de Retenção.",
    # valuation
    "ev_ebitda": "EV/EBITDA = (Market Cap + Dívida Líquida) / EBITDA.",
    "ev_ebit": "EV/EBIT = (Market Cap + Dívida Líquida) / EBIT.",
    "ev_fcf": "EV/FCF = (Market Cap + Dívida Líquida) / Fluxo de Caixa Livre.",
    "ev_sales": "EV/Sales = Enterprise Value / Receita Líquida.",
    "p_ebit": "P/EBIT = Preço da Ação / EBIT por ação.",
    "p_fcf": "P/FCF = Preço da Ação / Fluxo de Caixa Livre por ação.",
    "p_fco": "P/FCO = Preço da Ação / Fluxo de Caixa Operacional por ação.",
    "graham_number": "Graham Number = √(22.5 × EPS × VPS). Preço justo segundo Graham.",
    "price_to_tangible_book": "P/VPA Tangível = Preço / Valor Patrimonial Tangível.",
    "magic_number": "Magic Number = EV/EBITDA × ROIC. Combina barato (EV/EBITDA) com qualidade (ROIC). <5 excelente, 5-15 bom, 15-30 justo, >30 caro.",
    # per_share
    "lpa": "P/L = Preço / Lucro por Ação. Quanto o mercado paga por R$1 de lucro.",
    "vpa": "P/VPA = Preço / Valor Patrimonial por Ação.",
    "dpa": "Dividend Yield = Dividendo por Ação / Preço.",
    "rps": "PSR = Preço / Receita por Ação.",
    # tax
    "effective_tax_rate": "Taxa de Tributo Efetiva = Imposto / Lucro Antes de Impostos.",
    # [v1.13] growth metrics (also set via MetricSpec.tooltip)
    "revenue_growth_3m": "Cresc. Receita 3M = (Receita TTM atual - Receita TTM há 3 meses) / |anterior|. Variação trimestral da receita.",
    "revenue_growth_1y": "Cresc. Receita 1A = (Receita TTM atual - Receita TTM há 1 ano) / |anterior|. Variação anual da receita.",
    "revenue_growth_5y": "Cresc. Receita 5A = (Receita TTM atual - Receita TTM há 5 anos) / |anterior|. Variação quinquenal da receita.",
    "net_income_growth_3m": "Cresc. Lucro 3M = (Lucro TTM atual - Lucro TTM há 3 meses) / |anterior|. Variação trimestral do lucro.",
    "net_income_growth_1y": "Cresc. Lucro 1A = (Lucro TTM atual - Lucro TTM há 1 ano) / |anterior|. Variação anual do lucro.",
    "net_income_growth_5y": "Cresc. Lucro 5A = (Lucro TTM atual - Lucro TTM há 5 anos) / |anterior|. Variação quinquenal do lucro.",
    "gross_profit_growth_3m": "Cresc. Resultado Bruto 3M = (Lucro Bruto TTM atual - há 3 meses) / |anterior|. Variação trimestral.",
    "gross_profit_growth_1y": "Cresc. Resultado Bruto 1A = (Lucro Bruto TTM atual - há 1 ano) / |anterior|. Variação anual.",
    "gross_profit_growth_5y": "Cresc. Resultado Bruto 5A = (Lucro Bruto TTM atual - há 5 anos) / |anterior|. Variação quinquenal.",
    # [v1.13] market risk metrics
    "coe": "COE = Rf + Beta × ERP. Custo de Oportunidade do Capital Próprio (CAPM). Rf=Selic, ERP=5.5% (Damodaran).",
    "beta": "Beta = Cov(Retorno ação, Retorno IBOV) / Var(IBOV). Sensibilidade ao mercado. >1 mais volátil, <1 menos volátil, <0 anticíclico.",
}


def get_tooltip(metric_name: str, spec: Any = None) -> str:
    """Return a tooltip string for a metric.

    Checks (in order):
      1. The local _METRIC_TOOLTIPS dict (curated, most detailed)
      2. MetricSpec.tooltip field (if spec is provided and has tooltip)
      3. Returns "" (no tooltip)
    """
    if metric_name in _METRIC_TOOLTIPS:
        return _METRIC_TOOLTIPS[metric_name]
    if spec is not None:
        # MetricSpec.tooltip field (v1.16.1+)
        tooltip = getattr(spec, "tooltip", None)
        if tooltip:
            return str(tooltip)
        # Fallback: try description/formula attributes
        desc = getattr(spec, "description", None) or getattr(spec, "formula", None)
        if desc:
            return str(desc)
    return ""
