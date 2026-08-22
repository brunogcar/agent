"""data_sources/ddm/acoes/catalog.py -- Schema + URL helpers for DDM Acoes.

DDM Acoes = Brazilian B3 tradable stocks scraped from dadosdemercado.com.br.
The /acoes page exposes a single HTML table (id="stocks") with 5 columns:
  - Ticker   | Nome     | Negocios      | Ultima (R$) | Variacao
  - 'PETR4'  | 'Petrobras' | '52.792.400' | '44,30'   | '+2,78%'

Unlike the other DDM sub-domains (inflation/juros/poupanca), acoes has NO
INDEX_CATALOG: there is only ONE page (/acoes), and the table is a flat
list of stocks (not a per-index historical series).

Storage: memory_db/ddm/acoes.db (per-subdomain DB in the DDM base folder,
mirroring ddm/juros.db + ddm/poupanca.db side-by-side layout).
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

# Canonical URL for the acoes page. No slug substitution (single page).
ACOES_PATH = "/acoes"


# Schema: one table per subdomain. Each row is a stock snapshot keyed by
# ticker (PK). Re-syncing replaces the entire snapshot (INSERT OR REPLACE).
#
# ref_date is the YYYY-MM-DD of the data (the day the snapshot was scraped -
# DDM does not expose a "data do pregao" column on the acoes page itself,
# so we use the scrape date as a proxy).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker        TEXT PRIMARY KEY,     -- 'PETR4'
    name          TEXT,                 -- 'Petrobras'
    negocios      INTEGER,              -- 52792400 (number of trades)
    last_price    REAL,                 -- 44.30 (BRL)
    variation     REAL,                 -- 2.78 (percentage, can be negative)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    ref_date      TEXT                  -- YYYY-MM-DD (scrape date)
);

CREATE INDEX IF NOT EXISTS idx_stocks_negocios  ON stocks(negocios);
CREATE INDEX IF NOT EXISTS idx_stocks_price     ON stocks(last_price);
CREATE INDEX IF NOT EXISTS idx_stocks_variation ON stocks(variation);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'acoes' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
"""


def ddm_data_dir():
    """Return the DDM base data directory (creates it if missing).

    All DDM DBs live in the SAME base folder (memory_db/ddm/), not
    per-subdomain subfolders. So inflation.db, acoes.db, juros.db,
    poupanca.db all sit side-by-side in memory_db/ddm/.
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
    """Return the path to acoes.db."""
    return ddm_data_dir() / "acoes.db"


def connect(read_only: bool = True):
    """Open a connection to acoes.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM acoes database not found at {path}. Run sync first."
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

    Idempotent: CREATE TABLE IF NOT EXISTS is safe to re-run.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def acoes_url() -> str:
    """Build the full URL for the acoes page."""
    return f"{API_BASE}{ACOES_PATH}"
