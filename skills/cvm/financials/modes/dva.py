"""Mode: dva -- Demonstração do Valor Adicionado (Value Added Statement).

Queries DFP (annual) + ITR (quarterly cumulative) DVA for the last N periods.
Returns the full DVA statement structured in 2 sections matching the CVM chart
of accounts + the private spreadsheet:

  Generation side (how wealth is created):
    1   = Receitas (Revenues)
    2   = Insumos (Inputs acquired from third parties)
    3   = Valor Adicionado Bruto (Gross Value Added)
    4   = Retenções (Retentions)
    5   = Valor Adicionado Líquido (Net Value Added produced)
    5.1 = Depreciação, Amortização e Baixas
    6   = Valor Adicionado Recebido em Transferência (VA Received)
    7   = Valor Adicionado Total a Distribuir (Total VA to Distribute)

  Distribution side (how wealth is distributed):
    8.1 = Pessoal (Personnel)
    8.2 = Impostos, Taxas e Contribuições (Government / Taxes)
    8.3 = Remuneração de Capital de Terceiros (Lenders / Interest)
    8.4 = Remuneração de Capital Próprio (Shareholders)

[v1.7] DVA is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the quarterly mode
handles BPA/BPP/DRE/DFC.

[v1.12] Refactored to use the shared `fetch_statement_data` helper from
`skills.cvm.financials.helpers` — eliminates ~150 lines of duplicated
fetch boilerplate. The `_DVA_CODES` list, `@register_mode` decorator, and
public function signature are preserved; only the fetch logic is delegated.

Registered as "dva" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.helpers import fetch_statement_data


# ── DVA account codes + labels ───────────────────────────────────────────────

_DVA_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP DVA uses 7.xx codes (NOT 1-8). Verified against real DFP data:
    # 7.08.xx is the dominant format (16808 rows for 7.08.04); 7.11.xx is a
    # newer format used by ~75 rows only. We query both.
    #
    # Generation side (how wealth is created):
    ("7.01",  "Receitas",                                            "generation"),
    ("7.03",  "Insumos Adquiridos de Terceiros",                     "generation"),
    ("7.04",  "Valor Adicionado Bruto",                              "generation"),
    ("7.05",  "Retenções",                                           "generation"),
    ("7.06",  "Valor Adicionado Líquido Produzido",                  "generation"),
    ("7.07",  "Vlr Adicionado Recebido em Transferência",            "generation"),
    ("7.08",  "Valor Adicionado Total a Distribuir",                 "generation"),
    ("7.10",  "Valor Adicionado Total a Distribuir (alt)",           "generation"),
    # Distribution side (how wealth is distributed) — old format (7.08.xx):
    ("7.08.01", "Pessoal",                                           "distribution"),
    ("7.08.02", "Impostos, Taxas e Contribuições",                   "distribution"),
    ("7.08.03", "Remuneração de Capital de Terceiros",               "distribution"),
    ("7.08.04", "Remuneração de Capital Próprio",                    "distribution"),
    # Distribution side — new format (7.11.xx, used by ~75 rows):
    ("7.11.01", "Pessoal (novo formato)",                            "distribution"),
    ("7.11.02", "Impostos, Taxas e Contribuições (novo formato)",    "distribution"),
    ("7.11.03", "Remuneração de Capital de Terceiros (novo)",        "distribution"),
    ("7.11.04", "Remuneração de Capital Próprio (novo)",             "distribution"),
]


# grupo filter: matches DVA (Demonstração de Valor Adicionado). The grupo
# field stores the full Portuguese statement name (e.g. "DF Consolidado -
# Demonstração de Valor Adicionado"), NOT the short "DVA" abbreviation.
_DVA_GRUPO_FILTER = "%Valor Adicionado%"


@register_mode(
    "dva",
    description=(
        "Demonstração do Valor Adicionado (DVA) — Value Added Statement. "
        "Returns the full DVA for the last N periods (annual or quarterly), "
        "structured in generation side (codes 1-7) + distribution side "
        "(codes 8.1-8.4). Shows how the company creates and distributes "
        "wealth across stakeholders (personnel, government, lenders, "
        "shareholders). DVA is available in both DFP (annual) and ITR "
        "(quarterly cumulative)."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def dva(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Demonstração do Valor Adicionado (DVA) for the last N periods.

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
          - If the company has no DVA data, returns status="not_found".

    [v1.12] Delegates to the shared `fetch_statement_data` helper from
    `skills.cvm.financials.helpers`. The `_DVA_CODES` list + grupo filter
    + statement name ("DVA") are passed as parameters; the helper owns the
    DFP/ITR fetch + periods-data assembly logic.
    """
    return fetch_statement_data(
        company=company,
        grupo_filter=_DVA_GRUPO_FILTER,
        codes=_DVA_CODES,
        periods=periods,
        consolidado=consolidado,
        quarterly=quarterly,
        statement_name="DVA",
    )
