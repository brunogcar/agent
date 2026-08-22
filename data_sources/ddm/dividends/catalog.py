"""data_sources/ddm/dividends/catalog.py -- Schema + URL constants for DDM Dividends.

DDM Dividends = Brazilian corporate dividend events scraped from
dadosdemercado.com.br/agenda-de-dividendos.

Single page, single table (class "normal-table"), ~200 rows.
Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento
Tipos:   Dividendo | JCP (Juros sobre Capital Proprio)

Storage: memory_db/ddm/dividends.db (per-subdomain DB, mirrors the
bcb/focus + ddm/juros + ddm/poupanca pattern of one DB per subdomain.
Sits alongside inflation.db / juros.db / poupanca.db in memory_db/ddm/.)
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

DIVIDENDS_URL = f"{API_BASE}/agenda-de-dividendos"

# 2 tipos published by DDM in the agenda de dividendos page.
TIPOS = ("Dividendo", "JCP")

# Canonical sort keys accepted by query_engine.dividends_list.
SORT_KEYS = (
    "value", "ticker", "tipo",
    "record_date", "ex_date", "payment_date",
)

# Schema: 2 tables.
#   - dividends       : one row per (ticker, record_date, tipo) observation.
#                       Stored as REAL value + ISO date strings (YYYY-MM-DD).
#   - sync_state      : single row (slug='dividends') with last sync info.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dividends (
    ticker        TEXT NOT NULL,
    tipo          TEXT,
    value         REAL,
    record_date   TEXT,
    ex_date       TEXT,
    payment_date  TEXT,
    synced_at     TEXT,
    PRIMARY KEY (ticker, record_date, tipo)
);

CREATE INDEX IF NOT EXISTS idx_div_ticker ON dividends(ticker);
CREATE INDEX IF NOT EXISTS idx_div_record ON dividends(record_date);
CREATE INDEX IF NOT EXISTS idx_div_ex     ON dividends(ex_date);
CREATE INDEX IF NOT EXISTS idx_div_pay    ON dividends(payment_date);
CREATE INDEX IF NOT EXISTS idx_div_tipo   ON dividends(tipo);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
"""


def ddm_data_dir():
    """Return the DDM base data directory (creates it if missing).

    Mirrors ddm/inflation/juros/poupanca: all DDM DBs live in the SAME
    base folder (memory_db/ddm/), not per-subdomain subfolders.
    dividends.db sits side-by-side with inflation.db, juros.db, poupanca.db.
    """
    from pathlib import Path
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        d = Path(memory_root) / "ddm"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "ddm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path():
    """Return the path to dividends.db (in memory_db/ddm/dividends.db)."""
    return ddm_data_dir() / "dividends.db"


def connect(read_only: bool = True):
    """Open a connection to dividends.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM dividends database not found at {path}. Run sync first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn):
    """Create tables if they don't exist.

    Idempotent: safe to call on every connect-for-write.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
