"""Mode: dfc -- Demonstração do Fluxo de Caixa (Cash Flow Statement).

Queries DFP (annual) + ITR (quarterly cumulative) DFC for the last N periods.
Returns the full DFC matching the CVM chart of accounts:

  6.01       = Caixa Líquido Atividades Operacionais (FCO) — 6628 rows
  6.01.01.02 = Depreciação e Amortização (Método Indireto) — 6021 rows
               The primary D&A code used by the `da` engine + `_extract_metrics`.
  6.02       = Caixa Líquido Atividades de Investimento (FCI) — 6627 rows
  6.03       = Caixa Líquido Atividades de Financiamento (FCF) — 6628 rows
  6.04       = Variação Cambial s/ Caixa e Equivalentes — [v1.11] NEW
  6.05       = Aumento (Redução) de Caixa e Equivalentes (net cash change)
               — [v1.11] NEW

DFC methods (two coexisting filer groups in CVM DFP):
  - DFC_MI (Método Indireto): 318873 rows — 98.6% of filers. D&A is reported
    under 6.01.01.02 ("Depreciação e Amortização") as a non-cash adjustment
    to net income.
  - DFC_MD (Método Direto): 4433 rows — 1.4% of filers (banks, insurers).
    D&A does NOT appear in a standardized sub-account under DFC_MD — the
    v1.2 fallback code 6.02.01.02 has 0 ROWS in real DFP data, and the
    v1.2 "alternative" code 6.01.04 turned out to be a MISLABEL (it is
    actually "Pagamentos à Fornecedores" with 11 rows, NOT D&A).
  - For DFC_MD filers, D&A is only recoverable via the description-search
    in `skills.cvm.calculations.engines.da` (`descricao LIKE '%deprec%'
    OR descricao LIKE '%amort%'`, scoped to `codigo LIKE '6.01.%'`).

[v1.11] DFC is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the BPA + BPP +
DRE + DVA modes handle their respective statements.

[v1.12] Refactored to use the shared `fetch_statement_data` helper from
`skills.cvm.financials.helpers` — eliminates ~150 lines of duplicated
fetch boilerplate. The `_DFC_CODES` list, `@register_mode` decorator, and
public function signature are preserved; only the fetch logic is delegated.

D&A code issues (CRITICAL — documented in DFC.md):
  - 6.01.01.02 = D&A indirect method — WORKS (6021 rows). Primary code.
  - 6.02.01.02 = D&A direct method — 0 ROWS in real DFP. Dead fallback
    code path (returns None silently). Kept for completeness.
  - 6.01.04    = MISLABELED — DB says "Pagamentos à Fornecedores" (11 rows).
    [v1.11] REMOVED from SUMMARY_CODES and from `_extract_metrics` fallback
    chain. Was incorrectly labeled "Depreciação e Amortização (DFC_MD alt)"
    in v1.2 — would have returned WRONG data (supplier payments, not D&A).

No grupo filter issues — DFC engines already use `grupo LIKE '%Fluxo de
Caixa%'` (correct, matches BOTH DFC_MI and DFC_MD statements).

Registered as "dfc" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.helpers import fetch_statement_data


# ── DFC account codes + labels ───────────────────────────────────────────────

_DFC_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP DFC uses 6.xx codes. Verified against real DFP data:
    #   6.01     — 6628 rows (FCO — operating)
    #   6.02     — 6627 rows (FCI — investing)
    #   6.03     — 6628 rows (FCF — financing)
    #   6.04     — Variação Cambial s/ Caixa e Equivalentes (NEW v1.11)
    #   6.05     — Aumento (Redução) de Caixa e Equivalentes (NEW v1.11)
    #   6.01.01.02 — D&A indirect method — 6021 rows (the primary D&A code)
    #
    # DFC methods (filers split between two coexisting methods):
    #   DFC_MI (Método Indireto): 318873 rows — 98.6% of filers
    #   DFC_MD (Método Direto):   4433 rows — 1.4% of filers (banks, insurers)
    #
    # D&A code issues — see DFC.md for full details:
    #   6.01.01.02 = D&A indirect method — WORKS (6021 rows)
    #   6.02.01.02 = D&A direct method fallback — 0 ROWS in real DFP (dead code)
    #   6.01.04    = MISLABELED "Pagamentos à Fornecedores" (11 rows) — removed
    #                from SUMMARY_CODES + _extract_metrics in v1.11
    ("6.01",       "Caixa Líquido Atividades Operacionais (FCO)",     "operating"),
    ("6.01.01.02", "Depreciação e Amortização",                       "da"),
    ("6.02",       "Caixa Líquido Atividades de Investimento (FCI)",  "investing"),
    ("6.03",       "Caixa Líquido Atividades de Financiamento (FCF)", "financing"),
    ("6.04",       "Variação Cambial s/ Caixa e Equivalentes",        "fx_change"),
    ("6.05",       "Aumento (Redução) de Caixa e Equivalentes",       "net_change"),
]


# grupo filter: matches BOTH DFC_MI (Método Indireto) AND DFC_MD (Método
# Direto). Codes 6.xx are unique to DFC, so the code-list filter
# (`codigo IN (...)`) is sufficient on its own — but the grupo filter is
# included as a safety net for future CVM schema changes.
_DFC_GRUPO_FILTER = "%Fluxo de Caixa%"


@register_mode(
    "dfc",
    description=(
        "Demonstração do Fluxo de Caixa (DFC) — Cash Flow Statement. Returns "
        "the full DFC for the last N periods (annual or quarterly), "
        "structured top-to-bottom (FCO → D&A → FCI → FCF → Variação Cambial "
        "→ Aumento/Redução de Caixa). DFC is available in both DFP (annual) "
        "and ITR (quarterly cumulative). Filters by grupo '%Fluxo de Caixa%' "
        "which matches BOTH DFC_MI (Método Indireto, 98.6% of filers) AND "
        "DFC_MD (Método Direto, 1.4% — banks + insurers). D&A comes from "
        "code 6.01.01.02 (indirect method, 6021 rows); the v1.2 DFC_MD "
        "fallback 6.02.01.02 has 0 rows in real DFP (dead code path, kept "
        "for completeness) and 6.01.04 was a MISLABEL ('Pagamentos à "
        "Fornecedores', NOT D&A) — removed in v1.11."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dfc", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dfc", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dfc", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def dfc(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Demonstração do Fluxo de Caixa (DFC) for the last N periods.

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
          - If the company has no DFC data, returns status="not_found".

    [v1.12] Delegates to the shared `fetch_statement_data` helper from
    `skills.cvm.financials.helpers`. The `_DFC_CODES` list + grupo filter
    + statement name ("DFC") are passed as parameters; the helper owns the
    DFP/ITR fetch + periods-data assembly logic.
    """
    return fetch_statement_data(
        company=company,
        grupo_filter=_DFC_GRUPO_FILTER,
        codes=_DFC_CODES,
        periods=periods,
        consolidado=consolidado,
        quarterly=quarterly,
        statement_name="DFC",
    )
