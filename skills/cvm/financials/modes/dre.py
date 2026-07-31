"""Mode: dre -- Demonstração do Resultado do Exercício (Income Statement).

Queries DFP (annual) + ITR (quarterly cumulative) DRE for the last N periods.
Returns the full DRE statement matching the CVM chart of accounts:

  3.01 = Receita Líquida (Revenue)
  3.02 = Custo dos Bens e Serviços Vendidos (COGS)
  3.03 = Resultado Bruto (Gross Profit)
  3.04 = Despesas Operacionais (Operating Expenses)
  3.05 = Resultado Antes dos Tributos sobre o Lucro (EBIT)
  3.06 = Resultado Financeiro (Financial Result)
  3.07 = Resultado Líquido das Operações Continuadas (Net Continuing Ops)
  3.08 = Imposto de Renda e Contribuição Social (Income Tax)
  3.09 = Lucro/Prejuízo Consolidado do Período (Net Income)
  3.11 = Lucro/Prejuízo Consolidado do Período (alt — some filers use this)

[v1.8] DRE is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the DVA + quarterly
modes handle BPA/BPP/DRE/DFC.

[v1.12] Refactored to use the shared `fetch_statement_data` helper from
`skills.cvm.financials.helpers` — eliminates ~150 lines of duplicated
fetch boilerplate. The `_DRE_CODES` list, `@register_mode` decorator, and
public function signature are preserved; only the fetch logic is delegated.

DRE vs DRA distinction:
  - grupo LIKE '%Demonstração do Resultado%'       = DRE (this mode)
  - grupo LIKE '%Demonstração de Resultado Abrangente%' = DRA (DIFFERENT
    statement — comprehensive income; NOT queried here)

Registered as "dre" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.helpers import fetch_statement_data


# ── DRE account codes + labels ───────────────────────────────────────────────

_DRE_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP DRE uses 3.xx codes. Verified against real DFP data:
    # 3.01-3.09 each have ~6628-6629 rows; 3.11 has 6377 rows (some filers
    # use 3.09 or 3.13 instead).
    #
    # Note on multiple labels per code (CVM chart changed over years):
    #   3.01 — some filers use "Receitas da Intermediação Financeira" (banks)
    #   3.03 — some filers use "Resultado Bruto Intermediação Financeira"
    #   3.05 — also labeled "Resultado Antes dos Tributos sobre o Lucro"
    #   3.06 — ALSO labeled "Imposto de Renda" by some filers (chart drift)
    #   3.07 — NOT in SUMMARY_CODES prior to v1.8 (added this version)
    #   3.08 — ALSO labeled "Operações Descontinuadas" by some filers
    #   3.09 — currently in SUMMARY_CODES as "Resultado Líquido (Continuadas)"
    #   3.11 — some filers use 3.09 or 3.13 instead (6377 vs 6629 rows)
    ("3.01",  "Receita Líquida de Vendas e/ou Serviços",                "revenue"),
    ("3.02",  "Custo dos Bens e/ou Serviços Vendidos",                  "costs"),
    ("3.03",  "Resultado Bruto",                                        "gross_profit"),
    ("3.04",  "Despesas Administrativas, Gerais e Comerciais",          "operating_expenses"),
    ("3.05",  "Resultado Antes do Resultado Financeiro e dos Tributos", "ebit"),
    ("3.06",  "Resultado Financeiro",                                   "financial_result"),
    ("3.07",  "Resultado Líquido das Operações Continuadas",            "net_continuing"),
    ("3.08",  "Imposto de Renda e Contribuição Social sobre o Lucro",   "tax"),
    ("3.09",  "Lucro/Prejuízo Consolidado do Período",                  "net_income"),
    ("3.11",  "Lucro/Prejuízo Consolidado do Período (alt)",            "net_income_alt"),
]


# grupo filter: DRE only. Excludes "Demonstração de Resultado Abrangente"
# (DRA) which is a different statement.
_DRE_GRUPO_FILTER = "%Demonstração do Resultado%"


@register_mode(
    "dre",
    description=(
        "Demonstração do Resultado do Exercício (DRE) — Income Statement. "
        "Returns the full DRE for the last N periods (annual or quarterly), "
        "structured top-to-bottom (Receita → Custos → Lucro Bruto → "
        "Despesas Operacionais → EBIT → Resultado Financeiro → Imposto de "
        "Renda → Lucro Líquido). DRE is available in both DFP (annual) and "
        "ITR (quarterly cumulative). Filters by grupo "
        "'%Demonstração do Resultado%' (NOT '%Resultado Abrangente%' — that "
        "is the separate DRA statement)."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def dre(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Demonstração do Resultado do Exercício (DRE) for the last N periods.

    Args:
        company: B3 ticker, name fragment, or CNPJ. Required.
        periods: Number of periods to return. Default: 5.
        consolidado: 1=consolidated (default), 0=individual.
        quarterly: 1=quarterly (ITR meses=3/6/9 + DFP meses=12),
                   0=annual only (DFP meses=12). Default: 0.

    Returns:
        Dict with:
          - status: "ok" or "not_found" / "error"
          - company: resolved company name
          - period_type: "annual" or "quarterly"
          - periods: list of {data_fim_exerc, meses, accounts: {codigo: {label, section, valor_brl}}}
            sorted newest-first.
          - If the company has no DRE data, returns status="not_found".

    [v1.12] Delegates to the shared `fetch_statement_data` helper from
    `skills.cvm.financials.helpers`. The `_DRE_CODES` list + grupo filter
    + statement name ("DRE") are passed as parameters; the helper owns the
    DFP/ITR fetch + periods-data assembly logic.
    """
    return fetch_statement_data(
        company=company,
        grupo_filter=_DRE_GRUPO_FILTER,
        codes=_DRE_CODES,
        periods=periods,
        consolidado=consolidado,
        quarterly=quarterly,
        statement_name="DRE",
    )
