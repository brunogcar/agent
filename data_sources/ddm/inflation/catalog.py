"""data_sources/ddm/inflation/catalog.py -- Schema + index catalog for DDM Inflation.

DDM Inflation = Brazilian inflation indices scraped from dadosdemercado.com.br.
Each index has its own page at /indices/{slug} with 2 HTML tables:
  1. Monthly matrix  (id="index-values")  -- year rows, Jan-Dez + Ano columns
  2. Historical monthly (class "normal-table") -- DESC monthly rows with
     month_value / year_acumulado / acumulado_12m

Storage: memory_db/ddm/inflation.db (per-subdomain DB in the DDM base folder)
the bcb/focus pattern of one DB per subdomain).
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

# Curated catalog of 3 inflation indices.
# Tuple shape: (name, category, description, unit)
#   category is always "Inflacao" for this subdomain (kept for parity with
#   the bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is always "%" (these are all percent variations).
INDEX_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "igp-m": ("IGP-M", "Inflacao",
              "Indice Geral de Precos - Mercado (FGV). Variacao mensal %.",
              "%"),
    "ipca":  ("IPCA",  "Inflacao",
              "Indice Nacional de Precos ao Consumidor Amplo (IBGE). "
              "Variacao mensal %.",
              "%"),
    "inpc":  ("INPC",  "Inflacao",
              "Indice Nacional de Precos ao Consumidor (IBGE). "
              "Variacao mensal %.",
              "%"),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (DDM pages use 'Jul/2026' strings).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS index_observations (
    slug            TEXT NOT NULL,
    ref_date        TEXT NOT NULL,        -- YYYY-MM (normalized from 'Jul/2026')
    month_value     REAL,                 -- variacao no mes (%)
    year_acumulado  REAL,                 -- acumulado no ano (%)
    acumulado_12m   REAL,                 -- acumulado 12 meses (%)
    synced_at       TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON index_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON index_observations(ref_date);

CREATE TABLE IF NOT EXISTS index_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "igp-m"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


def ddm_data_dir():
    """Return the DDM base data directory (creates it if missing).

    [v5] All DDM DBs live in the SAME base folder (memory_db/ddm/), not
    per-subdomain subfolders. So inflation.db, stocks.db, funds.db, etc.
    all sit side-by-side in memory_db/ddm/.
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
    """Return the path to inflation.db."""
    return ddm_data_dir() / "inflation.db"


def connect(read_only: bool = True):
    """Open a connection to inflation.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM inflation database not found at {path}. Run sync first."
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
    """Create tables if they don't exist + populate index_catalog.

    Idempotent: INSERT OR REPLACE refreshes metadata on every sync.
    """
    conn.executescript(SCHEMA_SQL)
    rows = [
        (slug, meta[0], meta[1], meta[2], meta[3])
        for slug, meta in INDEX_CATALOG.items()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO index_catalog "
        "(slug, name, category, description, unit) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
