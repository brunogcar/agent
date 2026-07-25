"""data_sources/cvm/vlmo/catalog.py -- Schema + paths for VLMO database.

Two tables:
  vlmo_documents  -- filing metadata (who filed, when, link to PDF)
  vlmo_movements  -- the actual insider trading transactions
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config import cfg

# ── Database path ────────────────────────────────────────────────────────────

def db_path() -> Path:
    """Return the path to the VLMO database.

    Uses the same directory as the other CVM databases (dfp.db, itr.db, etc.)
    by importing dfp_db_path from _db.py and using its parent directory.
    """
    from data_sources.cvm._db import dfp_db_path
    return dfp_db_path().parent / "vlmo.db"


def connect(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the VLMO database."""
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"VLMO database not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Filing metadata (one row per VLMO document filed)
CREATE TABLE IF NOT EXISTS vlmo_documents (
    Categoria                   TEXT,
    CNPJ_Companhia              TEXT,
    Codigo_CVM                  TEXT,
    Data_Entrega                TEXT,
    Data_Referencia             TEXT,
    Link_Download               TEXT,
    Nome_Companhia              TEXT,
    Protocolo_Entrega           TEXT,
    Tipo                        TEXT,
    Tipo_Apresentacao           TEXT,
    Versao                      INTEGER,
    Motivo_Reapresentacao       TEXT
);

CREATE INDEX IF NOT EXISTS idx_vlmo_doc_cnpj ON vlmo_documents(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_vlmo_doc_cvm ON vlmo_documents(Codigo_CVM);
CREATE INDEX IF NOT EXISTS idx_vlmo_doc_ref ON vlmo_documents(Data_Referencia);

-- Insider trading movements (the valuable data — one row per transaction)
CREATE TABLE IF NOT EXISTS vlmo_movements (
    CNPJ_Companhia              TEXT,
    Data_Referencia             TEXT,
    Nome_Companhia              TEXT,
    Preco_Unitario              REAL,
    Tipo_Ativo                  TEXT,
    Versao                      INTEGER,
    Descricao_Movimentacao      TEXT,
    Intermediario               TEXT,
    Tipo_Cargo                  TEXT,
    Empresa                     TEXT,
    Data_Movimentacao           TEXT,
    Tipo_Movimentacao           TEXT,
    Quantidade                  REAL,
    Caracteristica_Valor_Mobiliario TEXT,
    Volume                      REAL,
    Tipo_Empresa                TEXT,
    Tipo_Operacao               TEXT
);

CREATE INDEX IF NOT EXISTS idx_vlmo_mov_cnpj ON vlmo_movements(CNPJ_Companhia);
CREATE INDEX IF NOT EXISTS idx_vlmo_mov_date ON vlmo_movements(Data_Movimentacao);
CREATE INDEX IF NOT EXISTS idx_vlmo_mov_tipo ON vlmo_movements(Tipo_Movimentacao);
CREATE INDEX IF NOT EXISTS idx_vlmo_mov_cargo ON vlmo_movements(Tipo_Cargo);

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
