"""
skills/cvm/catalog.py -- Schema constants for rapina.db (rapinav2 format).

SOURCE: Empirical inspection of rapina.db (1.5 GB, 12.5M rows in contas).
        See inspect_rapina_db_v2.py for the full schema discovery run.

RAPINA.DB STRUCTURE (3 tables matter)
--------------------------------------

empresas (10,840 rows) -- one row PER COMPANY PER YEAR
  id       INTEGER  -- PK used as FK in contas.id_empresa
  cnpj     VARCHAR  -- formatted: "33.000.167/0001-01"
  nome     VARCHAR  -- full company name
  ano      INT      -- the year this record covers (2010-2026)

  CRITICAL: same company appears multiple times with different ids across years.
  Petrobras: id=114 (ano=2025), id=5564 (ano=2024), id=11617 (ano=2023), ...
  To query multiple years we collect ALL ids for a CNPJ first, then query contas.

contas (12.5M rows) -- all financial statement data
  id_empresa  INTEGER  -- FK -> empresas.id (year-specific)
  codigo      VARCHAR  -- CVM account code ("1", "3.01", "3.04.02", ...)
  descr       VARCHAR  -- human label (varies slightly across companies)
  grupo       VARCHAR  -- statement type: BPA | BPP | DRE | DFC | DVA
  consolidado INTEGER  -- 1=consolidated, 0=individual
  data_ini_exerc VARCHAR  -- period start date (YYYY-MM-DD, may be empty)
  data_fim_exerc VARCHAR  -- period end date  (YYYY-MM-DD) -- use this for sorting
  meses       INTEGER  -- period length in months (see MESES below)
  valor       REAL     -- raw stored value
  escala      INTEGER  -- multiplier: real_value = valor * escala
  moeda       VARCHAR  -- currency ("R$")

isin (68,527 rows) -- ticker/ISIN/CNPJ cross-reference
  key     TEXT  -- internal key
  ticker  TEXT  -- B3 ticker (numeric format for funds, e.g. "0010")
  cnpj    TEXT  -- NUMERIC format (no dots/slashes): "33000167000101"
  nome    TEXT  -- company name

  NOTE: isin.cnpj uses numeric format; empresas.cnpj uses formatted format.
  To join: strip ".", "/", "-" from empresas.cnpj for comparison.
  NOTE: isin contains mostly investment funds. B3 stock tickers (PETR4, VALE3)
  are NOT in isin -- use empresas.nome or empresas.cnpj for lookup instead.
  isin is kept for future ISIN->CNPJ joins with b3_api Instruments table.

MESES -- period length in months
  meses=3  -> Q1 (3 months, Jan-Mar for Dec fiscal year)
  meses=6  -> H1 cumulative (6 months, Jan-Jun) -- NOT standalone Q2
  meses=9  -> 9 months cumulative (Jan-Sep)      -- NOT standalone Q3
  meses=12 -> Full year annual (DFP filing)
  meses=15 -> Rare: 15-month first fiscal period (314 rows total, ignorable)

  DECISION: meses=3/6/9/12 all come from separate CVM filings (ITR quarterly,
  DFP annual). They are CUMULATIVE within the fiscal year. True standalone Q2
  would require subtracting meses=3 from meses=6. This v1 returns them as-filed
  with clear labels. Standalone quarter computation deferred to v2.

GRUPO -- statement type codes
  BPA -> Balanço Patrimonial Ativo (Balance Sheet -- Assets)
  BPP -> Balanço Patrimonial Passivo (Balance Sheet -- Liabilities + Equity)
  DRE -> Demonstração do Resultado (Income Statement)
  DFC -> Demonstração do Fluxo de Caixa (Cash Flow Statement)
  DVA -> Demonstração do Valor Adicionado (Value Added Statement)

ACCOUNT CODE CONVENTIONS
  Codes follow hierarchical dot notation: "3.04.02" is child of "3.04" of "3"
  Top-level codes (no dot or single digit) are subtotals/totals.
  The code is the stable identifier across companies -- descr varies slightly.
  All codes discovered empirically from 10,800+ companies.
"""

from __future__ import annotations

from pathlib import Path
from core.config import cfg


# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------

# DECISION: rapina.db lives in memory_db/cvm/ alongside chromadb and b3 data.
# rapinav2 is run externally to update it (rapinav2 atualizar --all).
# This skill reads it as read-only -- never writes to it.
CVM_DB_PATH: Path = cfg.memory_root / "cvm" / "rapina.db"


# ---------------------------------------------------------------------------
# Statement type groups
# ---------------------------------------------------------------------------

GRUPOS = {
    "BPA": "Balanço Patrimonial Ativo (Assets)",
    "BPP": "Balanço Patrimonial Passivo (Liabilities & Equity)",
    "DRE": "Demonstração do Resultado (Income Statement)",
    "DFC": "Demonstração do Fluxo de Caixa (Cash Flow)",
    "DVA": "Demonstração do Valor Adicionado (Value Added)",
}

# Maps meses value to human-readable period label
MESES_LABELS = {
    3:  "Q1 (3m)",
    6:  "H1 (6m cumul.)",
    9:  "9m cumul.",
    12: "Annual (12m)",
    15: "15m (special)",
}


# ---------------------------------------------------------------------------
# Resumo account code map
# ---------------------------------------------------------------------------
# These are the key financial metrics that make up the "resumo" view.
# Each entry: (codigo, grupo, label_pt, label_en)
# Verified against 10,800+ companies -- all present in >98% of records.
#
# NOTE ON 3.11 vs 3.03:
#   3.03 = Resultado Bruto (Gross Profit) -- what rapina calls "Resultado Bruto"
#   3.11 = Lucro/Prejuízo Consolidado (Net Income) -- the bottom line
#   Both are included. Some older rapinav2 docs label 3.11 as "Resultado Bruto"
#   but inspection shows 3.11 is Net Income. We use both with correct labels.
#
# NOTE ON EQUITY (2.03):
#   BPP 2.03 is "Patrimônio Líquido Consolidado" or "Patrimônio Líquido"
#   depending on company. The code is stable; descr varies. We use the code.

RESUMO_ACCOUNTS: list[tuple[str, str, str, str]] = [
    # (codigo, grupo, label_pt, label_en)

    # Income Statement
    ("3.01", "DRE", "Receita Líquida",              "Net Revenue"),
    ("3.02", "DRE", "Custo dos Bens/Serviços",      "Cost of Goods Sold"),
    ("3.03", "DRE", "Resultado Bruto",               "Gross Profit"),
    ("3.05", "DRE", "EBIT",                          "EBIT (Operating Result)"),
    ("3.06", "DRE", "Resultado Financeiro",          "Financial Result"),
    ("3.07", "DRE", "Resultado Antes dos Tributos",  "Pre-tax Income"),
    ("3.08", "DRE", "Imposto de Renda/CSLL",         "Income Tax"),
    ("3.11", "DRE", "Lucro/Prejuízo Líquido",        "Net Income"),

    # Balance Sheet -- Assets
    ("1",    "BPA", "Ativo Total",                   "Total Assets"),
    ("1.01", "BPA", "Ativo Circulante",              "Current Assets"),
    ("1.01.01", "BPA", "Caixa e Equivalentes",       "Cash & Equivalents"),
    ("1.02", "BPA", "Ativo Não Circulante",          "Non-Current Assets"),

    # Balance Sheet -- Liabilities & Equity
    ("2",    "BPP", "Passivo Total",                 "Total Liabilities"),
    ("2.01", "BPP", "Passivo Circulante",            "Current Liabilities"),
    ("2.02", "BPP", "Passivo Não Circulante",        "Non-Current Liabilities"),
    ("2.03", "BPP", "Patrimônio Líquido",            "Shareholders' Equity"),

    # Cash Flow
    ("6.01", "DFC", "Caixa Operacional",             "Operating Cash Flow"),
    ("6.02", "DFC", "Caixa de Investimentos",        "Investing Cash Flow"),
    ("6.03", "DFC", "Caixa de Financiamentos",       "Financing Cash Flow"),
    ("6.05", "DFC", "Variação de Caixa",             "Net Change in Cash"),
]

# Quick lookup: (codigo, grupo) -> (label_pt, label_en)
RESUMO_LOOKUP: dict[tuple[str, str], tuple[str, str]] = {
    (code, grupo): (lpt, len_)
    for code, grupo, lpt, len_ in RESUMO_ACCOUNTS
}

# All resumo codes by grupo for efficient SQL IN clauses
RESUMO_BY_GRUPO: dict[str, list[str]] = {}
for code, grupo, _, __ in RESUMO_ACCOUNTS:
    RESUMO_BY_GRUPO.setdefault(grupo, []).append(code)


# ---------------------------------------------------------------------------
# CNPJ normalization helpers
# ---------------------------------------------------------------------------

def normalize_cnpj(cnpj: str) -> str:
    """
    Strip formatting from CNPJ to numeric-only: "33.000.167/0001-01" -> "33000167000101"
    Used to join empresas.cnpj (formatted) with isin.cnpj (numeric).
    """
    return "".join(c for c in cnpj if c.isdigit())


def format_cnpj(cnpj: str) -> str:
    """
    Format a numeric CNPJ: "33000167000101" -> "33.000.167/0001-01"
    """
    d = "".join(c for c in cnpj if c.isdigit())
    if len(d) != 14:
        return cnpj  # return as-is if not 14 digits
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def real_value(valor: float, escala: int) -> float:
    """
    Convert stored value to real R$ value.
    rapinav2 stores values / escala, so real = valor * escala.
    """
    return valor * escala
