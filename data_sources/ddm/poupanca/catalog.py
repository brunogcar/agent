"""data_sources/ddm/poupanca/catalog.py -- Schema + index catalog for DDM Poupanca.

DDM Poupanca = Brazilian savings-account monthly yield scraped from
dadosdemercado.com.br. The poupanca page has ONLY 1 HTML table (the monthly
matrix - id="index-values") with 12 month columns (Jan..Dez) and NO "Ano"
acumulado column.

There is NO historical table on the page. The historical series is
DERIVED from the matrix at fetch-time (see fetcher.flatten_matrix_to_observations):
  - month_value        = cell value (monthly yield %)
  - acumulado_no_ano   = SUM of all months in same year UP TO that month
                         (year-to-date cumulative return)
  - acumulado_12m      = SUM of the last 12 months (rolling cumulative return)

IMPORTANT: Poupanca uses SUM (not AVERAGE like juros) because the monthly
yield is already a percentage return - summing them produces the cumulative
return. This matches the analyst's Google Sheet layout.

Storage: memory_db/ddm/poupanca.db (per-subdomain DB, mirrors the juros +
inflation pattern of one DB per subdomain. Sits alongside inflation.db +
juros.db in the shared memory_db/ddm/ folder.)
"""

from __future__ import annotations

API_BASE = "https://www.dadosdemercado.com.br"

# Curated catalog of 1 poupanca index.
# Tuple shape: (name, category, description, unit)
#   category is "Renda Fixa" for this subdomain (kept for parity with the
#   bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is "%" (monthly yield %).
POUPANCA_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "poupanca": ("Poupanca", "Renda Fixa",
                 "Poupanca - rendimento mensal. Taxa de rendimento da caderneta "
                 "de poupanca no mes (%).",
                 "%"),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (the matrix cells are keyed by year + Portuguese month
# label like 'Jul').
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS poupanca_observations (
    slug             TEXT NOT NULL,
    ref_date         TEXT NOT NULL,        -- YYYY-MM (derived from matrix cell)
    month_value      REAL,                 -- monthly yield (%)
    acumulado_no_ano REAL,                 -- year-to-date SUM (%)
    acumulado_12m    REAL,                 -- rolling 12-month SUM (%)
    synced_at        TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON poupanca_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON poupanca_observations(ref_date);

CREATE TABLE IF NOT EXISTS poupanca_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "poupanca"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


def ddm_data_dir():
    """Return the DDM poupanca data directory (creates it if missing).

    Layout mirrors the bcb/sgs + bcb/focus + ddm/juros per-subdomain DB
    convention:
      memory_root/ddm/                (when core.config.cfg.memory_root is set)
      memory_db/ddm/                  (fallback relative to cwd)

    NOTE: poupanca.db lives in the SAME parent folder as inflation.db +
    juros.db (memory_db/ddm/) - all are per-subdomain DBs under the ddm
    domain folder, not under their own subdomain folder. This keeps the
    ddm folder tidy (inflation.db + juros.db + poupanca.db side-by-side).
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
    """Return the path to poupanca.db (in memory_db/ddm/poupanca.db)."""
    return ddm_data_dir() / "poupanca.db"


def connect(read_only: bool = True):
    """Open a connection to poupanca.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"DDM poupanca database not found at {path}. Run sync first."
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
    """Create tables if they don't exist + populate poupanca_catalog.

    Idempotent: INSERT OR REPLACE refreshes metadata on every sync.
    """
    conn.executescript(SCHEMA_SQL)
    rows = [
        (slug, meta[0], meta[1], meta[2], meta[3])
        for slug, meta in POUPANCA_CATALOG.items()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO poupanca_catalog "
        "(slug, name, category, description, unit) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
