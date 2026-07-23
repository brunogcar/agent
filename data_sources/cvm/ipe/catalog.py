"""data_sources/cvm/ipe/catalog.py -- Schema constants for IPE (Informações Periódicas e Eventuais).

IPE = material events filed by publicly listed companies (earnings releases,
dividend announcements, board changes, M&A, regulatory filings, etc.).

This is the EVENT INDEX — not the document content itself. Link_Download
points to the actual PDF/XML on CVM's servers.

Simplest of the CVM data sources: single table, single CSV per ZIP.
"""

from __future__ import annotations

# ── URL pattern ──────────────────────────────────────────────────────────────

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS"
URL_PATTERN = f"{CVM_BASE_URL}/ipe_cia_aberta_{{year}}.zip"

# IPE data starts in 2003 (earliest available)
FIRST_YEAR = 2003

# ── Encoding ─────────────────────────────────────────────────────────────────

CSV_ENCODING = "iso-8859-1"
CSV_DELIMITER = ";"

# ── SQL schema ───────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eventos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj             TEXT NOT NULL,
    cd_cvm           TEXT,
    nome             TEXT,
    data_entrega     TEXT,
    data_referencia  TEXT,
    categoria        TEXT,
    tipo             TEXT,
    especie          TEXT,
    assunto          TEXT,
    tipo_apresentacao TEXT,
    versao           INTEGER DEFAULT 1,
    protocolo        TEXT NOT NULL,
    link_download    TEXT,
    ano_origem       INTEGER,
    UNIQUE(protocolo)
);

CREATE INDEX IF NOT EXISTS idx_ipe_cnpj ON eventos(cnpj);
CREATE INDEX IF NOT EXISTS idx_ipe_cd_cvm ON eventos(cd_cvm);
CREATE INDEX IF NOT EXISTS idx_ipe_data_entrega ON eventos(data_entrega);
CREATE INDEX IF NOT EXISTS idx_ipe_categoria ON eventos(categoria);
CREATE INDEX IF NOT EXISTS idx_ipe_tipo ON eventos(tipo);

CREATE TABLE IF NOT EXISTS sync_state (
    year       INTEGER PRIMARY KEY,
    synced_at  TEXT NOT NULL,
    rows_added INTEGER DEFAULT 0,
    duration_s REAL DEFAULT 0
);
"""

# ── CSV column mapping (from meta_ipe_cia_aberta.txt) ───────────────────────

CSV_COLUMNS = {
    "CNPJ_Companhia":    "cnpj",
    "Codigo_CVM":        "cd_cvm",
    "Nome_Companhia":    "nome",
    "Data_Entrega":      "data_entrega",
    "Data_Referencia":   "data_referencia",
    "Categoria":         "categoria",
    "Tipo":              "tipo",
    "Especie":           "especie",
    "Assunto":           "assunto",
    "Tipo_Apresentacao": "tipo_apresentacao",
    "Versao":            "versao",
    "Protocolo_Entrega": "protocolo",
    "Link_Download":     "link_download",
}
