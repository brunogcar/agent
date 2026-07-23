"""data_sources/cvm/fre/catalog.py -- Schema constants for FRE (Formulário de Referência).

FRE = Formulário de Referência (Reference Form). Annual filing covering:
  - Shareholder composition (posicao_acionaria)
  - Free float / shareholder counts (distribuicao_capital)
  - Executive/board compensation (remuneracao_total_orgao)
  - Stock capital + share counts (capital_social)
  - Filing index (documentos)

Unlike DFP/ITR (financial statements), FRE is corporate governance +
ownership + compensation data. No meses/flow/snapshot concept.

The FRE ZIP contains 50+ CSVs, but we import only the 5 most analytically
useful for stock analysis. The rest are text-heavy governance sections
accessible via link_doc (download URL for the full document).
"""

from __future__ import annotations

# ── URL pattern ──────────────────────────────────────────────────────────────

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS"
URL_PATTERN = f"{CVM_BASE_URL}/fre_cia_aberta_{{year}}.zip"

# FRE data starts in 2010 (same as DFP)
FIRST_YEAR = 2010

# ── Encoding ─────────────────────────────────────────────────────────────────

CSV_ENCODING = "iso-8859-1"
CSV_DELIMITER = ";"

# ── The 5 tables we import (out of 50+ in the ZIP) ───────────────────────────

FRE_TABLES = {
    "documentos": {
        "csv_prefix": "fre_cia_aberta_",
        "description": "Filing index: ID_DOC, CNPJ, CD_CVM, dates, link to full document",
    },
    "posicao_acionaria": {
        "csv_prefix": "fre_cia_aberta_posicao_acionaria_",
        "description": "Shareholder composition: who owns how much (ON/PN/total %)",
    },
    "distribuicao_capital": {
        "csv_prefix": "fre_cia_aberta_distribuicao_capital_",
        "description": "Free float: % shares in circulation, shareholder counts",
    },
    "remuneracao_orgao": {
        "csv_prefix": "fre_cia_aberta_remuneracao_total_orgao_",
        "description": "Executive/board compensation: salary, bonus, stock-based",
    },
    "capital_social": {
        "csv_prefix": "fre_cia_aberta_capital_social_",
        "description": "Stock capital: share counts (ON/PN/total), capital value",
    },
}

# ── SQL schema (created by sync_engine) ──────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documentos (
    id_doc      INTEGER PRIMARY KEY,
    cnpj        TEXT,
    cd_cvm      TEXT,
    nome        TEXT,
    categ_doc   TEXT,
    dt_receb    TEXT,
    dt_refer    TEXT,
    versao      INTEGER,
    link_doc    TEXT,
    ano_origem  INTEGER
);

CREATE TABLE IF NOT EXISTS posicao_acionaria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj            TEXT,
    id_documento    INTEGER,
    data_referencia TEXT,
    versao          INTEGER,
    nome_companhia  TEXT,
    acionista       TEXT,
    cpf_cnpj_acionista TEXT,
    tipo_pessoa     TEXT,
    nacionalidade   TEXT,
    acionista_controlador TEXT,
    participante_acordo_acionistas TEXT,
    pct_on          REAL,
    pct_pn          REAL,
    pct_total       REAL,
    qtd_on          INTEGER,
    qtd_pn          INTEGER,
    qtd_total       INTEGER,
    UNIQUE(id_documento, cpf_cnpj_acionista)
);

CREATE TABLE IF NOT EXISTS distribuicao_capital (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj            TEXT,
    id_documento    INTEGER,
    data_referencia TEXT,
    versao          INTEGER,
    nome_companhia  TEXT,
    pct_on_circulacao     REAL,
    pct_pn_circulacao     REAL,
    pct_total_circulacao  REAL,
    qtd_on_circulacao     INTEGER,
    qtd_pn_circulacao     INTEGER,
    qtd_total_circulacao  INTEGER,
    qtd_acionistas_pf     INTEGER,
    qtd_acionistas_pj     INTEGER,
    qtd_acionistas_inst   INTEGER,
    data_ultima_assembleia TEXT,
    UNIQUE(id_documento)
);

CREATE TABLE IF NOT EXISTS remuneracao_orgao (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj            TEXT,
    id_documento    INTEGER,
    data_referencia TEXT,
    versao          INTEGER,
    nome_companhia  TEXT,
    orgao           TEXT,
    dt_ini_exercicio TEXT,
    dt_fim_exercicio TEXT,
    num_membros     REAL,
    num_membros_remunerados REAL,
    salario         REAL,
    beneficios      REAL,
    bonus           REAL,
    participacao_resultados REAL,
    baseada_acoes   REAL,
    total_remuneracao REAL,
    total_remuneracao_orgao REAL,
    UNIQUE(id_documento, orgao, dt_ini_exercicio)
);

CREATE TABLE IF NOT EXISTS capital_social (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj            TEXT,
    id_documento    INTEGER,
    data_referencia TEXT,
    versao          INTEGER,
    nome_companhia  TEXT,
    tipo_capital    TEXT,
    valor_capital   REAL,
    qtd_acoes_on    INTEGER,
    qtd_acoes_pn    INTEGER,
    qtd_acoes_total INTEGER,
    data_aprovacao  TEXT,
    UNIQUE(id_documento, tipo_capital)
);

CREATE TABLE IF NOT EXISTS sync_state (
    year             INTEGER PRIMARY KEY,
    synced_at        TEXT,
    rows_documentos  INTEGER,
    rows_posicao     INTEGER,
    rows_distrib     INTEGER,
    rows_remuneracao INTEGER,
    rows_capital     INTEGER,
    duration_s       REAL
);

CREATE INDEX IF NOT EXISTS idx_doc_cnpj ON documentos(cnpj);
CREATE INDEX IF NOT EXISTS idx_doc_cd_cvm ON documentos(cd_cvm);
CREATE INDEX IF NOT EXISTS idx_pos_cnpj ON posicao_acionaria(cnpj);
CREATE INDEX IF NOT EXISTS idx_dist_cnpj ON distribuicao_capital(cnpj);
CREATE INDEX IF NOT EXISTS idx_rem_cnpj ON remuneracao_orgao(cnpj);
CREATE INDEX IF NOT EXISTS idx_cap_cnpj ON capital_social(cnpj);
"""
