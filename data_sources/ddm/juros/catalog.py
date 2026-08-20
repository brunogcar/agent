"""data_sources/ddm/juros/catalog.py -- Schema + index catalog for DDM Juros.

DDM Juros = Brazilian interest-rate indices scraped from dadosdemercado.com.br.
Each index has its own page at /indices/{slug} with ONLY 1 HTML table:
  1. Monthly matrix  (id="index-values")  -- year rows, Jan-Dez columns only
                                              (NO "Ano" acumulado column).

There is NO historical table on these pages. The historical series is
DERIVED from the matrix at fetch-time (see fetcher.flatten_matrix_to_observations):
  - month_value   = cell value (daily rate %)
  - media_no_ano  = AVERAGE of all months in same year UP TO that month
  - media_12m     = AVERAGE of the last 12 months (rolling)

Storage: memory_db/ddm/juros.db (per-subdomain DB, mirrors the bcb/focus
pattern of one DB per subdomain. Sits alongside inflation.db in the
shared memory_db/ddm/ folder.)
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

# Curated catalog of 3 juros indices.
# Tuple shape: (name, category, description, unit)
#   category is always "Juros" for this subdomain (kept for parity with
#   the bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is always "% a.a." (annual rate - these are daily rates quoted as
#   annualized %).
JUROS_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "selic":      ("Selic",      "Juros",
                   "Taxa Selic diaria (BCB). Taxa media ajustada dos bancos "
                   "no SELIC, % a.a.",
                   "% a.a."),
    "meta-selic": ("Meta Selic", "Juros",
                   "Meta para a taxa Selic definida pelo Copom (Comite de "
                   "Politica Monetaria), % a.a.",
                   "% a.a."),
    "cdi":        ("CDI",        "Juros",
                   "Certificado de Deposito Interbancario. Taxa media dos "
                   "financiamentos diarios no mercado interbank, % a.a.",
                   "% a.a."),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (the matrix cells are keyed by year + Portuguese month
# label like 'Jul').
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS juros_observations (
    slug          TEXT NOT NULL,
    ref_date      TEXT NOT NULL,        -- YYYY-MM (derived from matrix cell)
    month_value   REAL,                 -- daily rate (% a.a.)
    media_no_ano  REAL,                 -- year-to-date average (% a.a.)
    media_12m     REAL,                 -- rolling 12-month average (% a.a.)
    synced_at     TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON juros_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON juros_observations(ref_date);

CREATE TABLE IF NOT EXISTS juros_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "selic"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


def ddm_data_dir():
    """Return the DDM juros data directory (creates it if missing).

    Layout mirrors the bcb/sgs + bcb/focus per-subdomain DB convention:
      memory_root/ddm/                (when core.config.cfg.memory_root is set)
      memory_db/ddm/                  (fallback relative to cwd)

    NOTE: juros.db lives in the SAME parent folder as inflation.db
    (memory_db/ddm/) - both are per-subdomain DBs under the ddm domain
    folder, not under their own subdomain folder.
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
    """Return the path to juros.db (in memory_db/ddm/juros.db)."""
    return ddm_data_dir() / "juros.db"


def connect(read_only: bool = True):
    """Open a connection to juros.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM juros database not found at {path}. Run sync first."
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
    """Create tables if they don't exist + populate juros_catalog.

    Idempotent: INSERT OR REPLACE refreshes metadata on every sync.
    """
    conn.executescript(SCHEMA_SQL)
    rows = [
        (slug, meta[0], meta[1], meta[2], meta[3])
        for slug, meta in JUROS_CATALOG.items()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO juros_catalog "
        "(slug, name, category, description, unit) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
