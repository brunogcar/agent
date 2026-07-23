"""data_sources/cvm/cad/catalog.py -- Schema constants for CAD (company register).

CAD = Cadastro de Companhias Abertas (company register).
A single CSV file (~1.5MB, ~3500 companies) updated weekly by CVM.
Contains: CNPJ, CD_CVM, legal/commercial names, status, sector, market type,
registration dates, cancellation info, address, contact, auditor.

This is the BRIDGE data source — CD_CVM links to DFP/ITR/FRE filings,
CNPJ links to B3 instruments. The primary use case is company resolution:
ticker → CNPJ → CD_CVM → financial statements.

Source: https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
Storage: memory_db/cvm/cad.db
"""

from __future__ import annotations

# ── URL ──────────────────────────────────────────────────────────────────────

CSV_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
CSV_ENCODING = "iso-8859-1"
CSV_DELIMITER = ";"

# ── All 46 columns from the CSV (in order) ───────────────────────────────────

ALL_COLS = [
    "CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "DT_REG", "DT_CONST",
    "DT_CANCEL", "MOTIVO_CANCEL", "SIT", "DT_INI_SIT", "CD_CVM",
    "SETOR_ATIV", "TP_MERC", "CATEG_REG", "DT_INI_CATEG",
    "SIT_EMISSOR", "DT_INI_SIT_EMISSOR", "CONTROLE_ACIONARIO",
    "TP_ENDER", "LOGRADOURO", "COMPL", "BAIRRO", "MUN", "UF", "PAIS", "CEP",
    "DDD_TEL", "TEL", "DDD_FAX", "FAX", "EMAIL",
    "TP_RESP", "RESP", "DT_INI_RESP",
    "LOGRADOURO_RESP", "COMPL_RESP", "BAIRRO_RESP", "MUN_RESP",
    "UF_RESP", "PAIS_RESP", "CEP_RESP",
    "DDD_TEL_RESP", "TEL_RESP", "DDD_FAX_RESP", "FAX_RESP", "EMAIL_RESP",
    "CNPJ_AUDITOR", "AUDITOR",
]

# Columns shown by default in search/lookup (skip contact noise)
DEFAULT_COLS = [
    "CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "CD_CVM",
    "SIT", "DT_INI_SIT", "SIT_EMISSOR", "DT_INI_SIT_EMISSOR",
    "DT_REG", "DT_CONST", "DT_CANCEL", "MOTIVO_CANCEL",
    "SETOR_ATIV", "TP_MERC", "CATEG_REG",
    "CONTROLE_ACIONARIO", "UF", "MUN",
    "EMAIL", "AUDITOR", "CNPJ_AUDITOR",
    "RESP", "EMAIL_RESP",
]

# ── SQL schema ───────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cia_aberta (
    {cols}
);

CREATE INDEX IF NOT EXISTS idx_cad_cnpj ON cia_aberta(CNPJ_CIA);
CREATE INDEX IF NOT EXISTS idx_cad_cd_cvm ON cia_aberta(CD_CVM);
CREATE INDEX IF NOT EXISTS idx_cad_denom_comerc ON cia_aberta(DENOM_COMERC);
CREATE INDEX IF NOT EXISTS idx_cad_denom_social ON cia_aberta(DENOM_SOCIAL);
CREATE INDEX IF NOT EXISTS idx_cad_sit ON cia_aberta(SIT);
CREATE INDEX IF NOT EXISTS idx_cad_setor ON cia_aberta(SETOR_ATIV);
CREATE INDEX IF NOT EXISTS idx_cad_controle ON cia_aberta(CONTROLE_ACIONARIO);
CREATE INDEX IF NOT EXISTS idx_cad_sit_emissor ON cia_aberta(SIT_EMISSOR);

CREATE TABLE IF NOT EXISTS sync_state (
    synced_at  TEXT PRIMARY KEY,
    rows       INTEGER DEFAULT 0,
    size_kb    REAL DEFAULT 0
);
""".format(cols=",\n    ".join(f"{c} TEXT" for c in ALL_COLS))
