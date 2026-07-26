"""data_sources/cvm/cgvn/catalog.py -- Schema + paths for CGVN database.

Two tables:
  cgvn_documents  -- filing metadata (who filed, when, link to PDF)
  cgvn_practices  -- governance practices (recommended vs adopted, chapter, principle)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path



# ── Database path ────────────────────────────────────────────────────────────

def db_path() -> Path:
    """Return the path to the CGVN database."""
    from data_sources.cvm._db import cgvn_db_path
    return cgvn_db_path()


def connect(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the CGVN database."""
    from data_sources.cvm._db import connect_cgvn
    return connect_cgvn(read_only=read_only)


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Filing metadata (one row per CGVN document filed)
CREATE TABLE IF NOT EXISTS cgvn_documents (
    Categoria                   TEXT,
    CNPJ_Companhia              TEXT,
    Codigo_CVM                  TEXT,
    Data_Entrega                TEXT,
    Data_Fim_Exercicio_Social   TEXT,
    Data_Inicio_Exercicio_Social TEXT,
    Data_Referencia             TEXT,
    ID_Documento                INTEGER,
    Link_Download               TEXT,
    Nome_Empresarial            TEXT,
    Versao                      INTEGER,
    Motivo_Reapresentacao       TEXT
);

CREATE INDEX IF NOT EXISTS idx_cgvn_doc_cnpj ON cgvn_documents(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_cgvn_doc_cvm ON cgvn_documents(Codigo_CVM);
CREATE INDEX IF NOT EXISTS idx_cgvn_doc_ref ON cgvn_documents(Data_Referencia);

-- Governance practices (the valuable data — one row per practice per filing)
CREATE TABLE IF NOT EXISTS cgvn_practices (
    CNPJ_Companhia              TEXT,
    Data_Referencia             TEXT,
    ID_Documento                INTEGER,
    Nome_Empresarial            TEXT,
    Versao                      INTEGER,
    ID_Item                     TEXT,
    Pratica_Recomendada         TEXT,
    Pratica_Adotada             TEXT,
    Capitulo                    TEXT,
    Principio                   TEXT,
    Explicacao                  TEXT
);

CREATE INDEX IF NOT EXISTS idx_cgvn_prac_cnpj ON cgvn_practices(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_cgvn_prac_ref ON cgvn_practices(Data_Referencia);
CREATE INDEX IF NOT EXISTS idx_cgvn_prac_item ON cgvn_practices(ID_Item);
CREATE INDEX IF NOT EXISTS idx_cgvn_prac_cap ON cgvn_practices(Capitulo);

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
