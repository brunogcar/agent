"""data_sources/cvm/fca/catalog.py -- Schema + paths for FCA database.

Three tables (the valuable ones from FCA's 9 CSVs):
  fca_geral             -- company registration (complements CAD)
  fca_valor_mobiliario  -- listed securities (ticker -> CNPJ + listing segment)
  fca_pais_estrangeiro  -- foreign listings (ADR/foreign exchanges)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path



# ── Database path ────────────────────────────────────────────────────────────

def db_path() -> Path:
    """Return the path to the FCA database."""
    from data_sources.cvm._db import fca_db_path
    return fca_db_path()


def connect(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the FCA database."""
    from data_sources.cvm._db import connect_fca
    return connect_fca(read_only=read_only)


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Company registration (complements CAD: fiscal year end, web page, control type, etc.)
CREATE TABLE IF NOT EXISTS fca_geral (
    Categoria_Registro_CVM              TEXT,
    CNPJ_Companhia                      TEXT,
    Codigo_CVM                          TEXT,
    Data_Alteracao_Exercicio_Social     TEXT,
    Data_Categoria_Registro_CVM         TEXT,
    Data_Constituicao                   TEXT,
    Data_Especie_Controle_Acionario     TEXT,
    Data_Nome_Empresarial               TEXT,
    Data_Referencia                     TEXT,
    Data_Registro_CVM                   TEXT,
    Data_Situacao_Emissor               TEXT,
    Data_Situacao_Registro_CVM          TEXT,
    Descricao_Atividade                 TEXT,
    Dia_Encerramento_Exercicio_Social   INTEGER,
    Especie_Controle_Acionario          TEXT,
    ID_Documento                        INTEGER,
    Mes_Encerramento_Exercicio_Social   INTEGER,
    Nome_Empresarial                    TEXT,
    Nome_Empresarial_Anterior           TEXT,
    Pagina_Web                          TEXT,
    Pais_Custodia_Valores_Mobiliarios   TEXT,
    Pais_Origem                         TEXT,
    Setor_Atividade                     TEXT,
    Situacao_Emissor                    TEXT,
    Situacao_Registro_CVM               TEXT,
    Versao                              INTEGER
);

CREATE INDEX IF NOT EXISTS idx_fca_geral_cnpj ON fca_geral(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_fca_geral_cvm ON fca_geral(Codigo_CVM);
CREATE INDEX IF NOT EXISTS idx_fca_geral_ref ON fca_geral(Data_Referencia);

-- Listed securities (THE valuable table: ticker -> CNPJ + listing segment)
CREATE TABLE IF NOT EXISTS fca_valor_mobiliario (
    CNPJ_Companhia                      TEXT,
    Codigo_Negociacao                   TEXT,
    Classe_Acao_Preferencial            TEXT,
    Composicao_BDR_Unit                 TEXT,
    Data_Fim_Listagem                   TEXT,
    Data_Fim_Negociacao                 TEXT,
    Data_Inicio_Listagem                TEXT,
    Data_Inicio_Negociacao              TEXT,
    Data_Referencia                     TEXT,
    Entidade_Administradora             TEXT,
    ID_Documento                        INTEGER,
    Mercado                             TEXT,
    Nome_Empresarial                    TEXT,
    Segmento                            TEXT,
    Sigla_Classe_Acao_Preferencial      TEXT,
    Sigla_Entidade_Administradora       TEXT,
    Valor_Mobiliario                    TEXT,
    Versao                              INTEGER
);

CREATE INDEX IF NOT EXISTS idx_fca_vm_ticker ON fca_valor_mobiliario(Codigo_Negociacao);
CREATE INDEX IF NOT EXISTS idx_fca_vm_cnpj ON fca_valor_mobiliario(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_fca_vm_ref ON fca_valor_mobiliario(Data_Referencia);

-- Foreign listings (ADR, foreign exchanges)
CREATE TABLE IF NOT EXISTS fca_pais_estrangeiro (
    CNPJ_Companhia                      TEXT,
    Data_Admissao_Negociacao            TEXT,
    Data_Referencia                     TEXT,
    ID_Documento                        INTEGER,
    Nome_Empresarial                    TEXT,
    Pais                                TEXT,
    Versao                              INTEGER
);

CREATE INDEX IF NOT EXISTS idx_fca_pe_cnpj ON fca_pais_estrangeiro(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_fca_pe_ref ON fca_pais_estrangeiro(Data_Referencia);

-- Sync state
CREATE TABLE IF NOT EXISTS sync_state (
    synced_at   TEXT,
    year        INTEGER,
    rows_synced INTEGER
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
