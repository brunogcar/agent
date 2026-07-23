"""data_sources/cvm/dfp/catalog.py -- Schema constants for DFP (annual filings).

CVM DFP (Demonstrações Financeiras Padronizadas) = annual financial statements.
Filed once per year. Contains:
  - BPA  (Balanço Patrimonial Ativo)      — assets snapshot
  - BPP  (Balanço Patrimonial Passivo)     — liabilities + equity snapshot
  - DRE  (Demonstração do Resultado)       — income statement (flow)
  - DFC  (Demonstração do Fluxo de Caixa)  — cash flow (flow)
  - DVA  (Demonstração de Valor Adicionado) — value added (flow)
  [v1.0.1 P0] DMPL excluded — 2D statement (COLUNA_DF) needs schema support.

All BPA/BPP rows have DT_INI_EXERC="" (snapshots, meses=12).
All DRE/DFC/DVA rows have DT_INI_EXERC!="" (flows, meses=12 for annual).

[v1.0.1 P0 fix] DMPL (Dem. Mutações do Patr. Líquido) is EXCLUDED from ingestion.
DMPL is a 2D statement — each CD_CONTA reports a different value per equity
component (COLUNA_DF field: Capital Social, Reservas, Lucros Acumulados, etc.).
The current schema has no COLUNA_DF column, so INSERT OR REPLACE silently
collides equity components — only the last one survives. rapinav2 also excludes
DMPL for this reason. DMPL will be added when the schema supports 2D statements.
"""

from __future__ import annotations

# ── Statement groups (GRUPO_DFP column in CVM CSV) ───────────────────────────

GRUPOS = {
    "BPA":     "Balanço Patrimonial Ativo",
    "BPP":     "Balanço Patrimonial Passivo",
    "DRE":     "Demonstração do Resultado",
    "DFC_MI":  "Demonstração do Fluxo de Caixa (Método Indireto)",
    "DFC_MD":  "Demonstração do Fluxo de Caixa (Método Direto)",
    "DVA":     "Demonstração de Valor Adicionado",
}

# Statements that are snapshots (DT_INI_EXERC = "")
SNAPSHOT_GRUPOS = {"BPA", "BPP"}

# Statements that are flows (DT_INI_EXERC != "")
# [v1.0.1 P0] DMPL removed — excluded from ingestion (2D statement, see docstring)
FLOW_GRUPOS = {"DRE", "DFC_MI", "DFC_MD", "DVA"}

# ── meses labels ─────────────────────────────────────────────────────────────

MESES_LABELS = {
    3:  "Q1 (3 months)",
    6:  "H1 (6 months cumulative)",
    9:  "9M (9 months cumulative)",
    12: "Annual (12 months)",
    15: "15-month transition (annual-style)",
}

# ── CVM CSV column names (from META files) ───────────────────────────────────

CSV_COLUMNS = [
    "CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM",
    "GRUPO_DFP", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
    "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA",
    "VL_CONTA", "ST_CONTA_FIXA",
]

# ── URL pattern ──────────────────────────────────────────────────────────────

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS"
URL_PATTERN = f"{CVM_BASE_URL}/dfp_cia_aberta_{{year}}.zip"

# DFP data starts in 2010
FIRST_YEAR = 2010

# ── Key account codes for resumo (summary) queries ───────────────────────────
# [v1.0.1 P1 fix] Corrected labels based on actual CVM DRE chart of accounts
# (verified against JHSF xlsx + CVM META files).
# Source: rapinav2/cmd/relatorio.go _tabelaContas (wildcard+description matching
# for EBIT/Patrimônio Líquido — we use the fixed codes that match for most companies;
# EBITDA/Margins/ROA/ROE are COMPUTED metrics, NOT raw CVM codes — they belong
# in the skills/ layer, not here).

RESUMO_ACCOUNTS = [
    # (codigo, grupo, label_pt) — all verified against actual CVM data
    ("1",       "BPA",    "Ativo Total"),
    ("2",       "BPP",    "Passivo Total"),
    ("2.03",    "BPP",    "Patrimônio Líquido"),
    ("3.01",    "DRE",    "Receita Líquida"),
    ("3.02",    "DRE",    "Custo dos Bens Vendidos"),
    ("3.03",    "DRE",    "Lucro Bruto"),
    ("3.05",    "DRE",    "EBIT"),  # Resultado Antes do Resultado Financeiro e dos Tributos
    ("3.06",    "DRE",    "Resultado Financeiro"),
    ("3.09",    "DRE",    "Resultado Líquido (Operações Continuadas)"),
    ("3.11",    "DRE",    "Lucro/Prejuízo Consolidado"),
    ("6.01",    "DFC_MI", "FCO (Fluxo de Caixa Operacional)"),
    ("6.02",    "DFC_MI", "FCI (Fluxo de Caixa de Investimento)"),
    ("6.03",    "DFC_MI", "FCF (Fluxo de Caixa de Financiamento)"),
]

# Build lookup: codigo → (grupo, label)
RESUMO_LOOKUP = {code: (grupo, label) for code, grupo, label in RESUMO_ACCOUNTS}

# ── Encoding ─────────────────────────────────────────────────────────────────

CSV_ENCODING = "iso-8859-1"
CSV_DELIMITER = ";"
