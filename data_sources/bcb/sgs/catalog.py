"""data_sources/bcb/sgs/catalog.py -- Schema + series catalog for BCB SGS.

BCB SGS = Sistema Gerenciador de Series Temporais (Brazilian Central Bank
Time Series Manager). Public, free, no auth required.

API: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados
  - ?formato=json&dataInicial=DD/MM/YYYY&dataFinal=DD/MM/YYYY
  - /ultimos/{n}?formato=json   (last N observations)
  - ?formato=csv                (Portuguese CSV, comma decimal)

Response shape (JSON):
  [{"data":"DD/MM/YYYY","valor":"<string-number>"}, ...]

All `valor` fields are STRINGS -- the fetcher parses them to float and
normalizes dates from DD/MM/YYYY to YYYY-MM-DD at the ingest boundary.

Storage: memory_db/bcb/sgs.db
"""

from __future__ import annotations

API_BASE = "https://api.bcb.gov.br/dados/serie"

# Curated catalog of 12 priority macro series.
# Tuple shape: (name, frequency, unit, category, description)
#   frequency in {daily, monthly, quarterly, annual}
#   category   in {Juros, Inflacao, Cambio, Atividade}
#   unit       is the raw unit reported by BCB (display layer formats it)
SERIES_CATALOG: dict[int, tuple[str, str, str, str, str]] = {
    # Juros (Interest rates)
    11:    ("Selic diaria",                 "daily",    "% a.d.",  "Juros",
            "Taxa de juros - Selic diaria (base 252). Valor diario, nao anualizado."),
    12:    ("CDI diaria",                   "daily",    "% a.d.",  "Juros",
            "Taxa de juros - CDI diaria (base 252). Valor diario, nao anualizado."),
    226:   ("TR (Taxa Referencial)",        "daily",    "%",       "Juros",
            "TR - Taxa Referencial. Base para poupanca e contratos."),
    432:   ("Meta Selic Copom",             "daily",    "% a.a.",  "Juros",
            "Meta para a taxa Selic definida pelo Copom"),
    4389:  ("Selic acumulada mes base 252", "daily",    "% a.a.",  "Juros",
            "Taxa de juros - Selic acumulada no mes anualizada base 252"),
    4390:  ("Selic acumulada mes",          "monthly",  "%",       "Juros",
            "Taxa de juros - Selic acumulada no mes"),
    # Inflacao (Inflation indices)
    433:   ("IPCA mensal",                  "monthly",  "%",       "Inflacao",
            "Indice Nacional de Precos ao Consumidor Amplo (IPCA) - variacao mensal"),
    189:   ("IGP-M mensal",                 "monthly",  "%",       "Inflacao",
            "Indice Geral de Precos do Mercado (IGP-M) - variacao mensal"),
    # Cambio (Exchange rates)
    1:     ("USD/BRL ptax venda",           "daily",    "R$",      "Cambio",
            "Dolar americano venda - taxa ptax. Serie diaria usada tambem para calcular medias mensais."),
    # Atividade (Economic activity)
    4380:  ("PIB nominal trimestral",       "quarterly","R$ mil",  "Atividade",
            "Produto Interno Bruto nominal - trimestral"),
    1619:  ("Salario minimo mensal",        "monthly",  "R$",      "Atividade",
            "Salario minimo mensal"),
}

# [v3] Schema uses the v1 sync_state shape (series_code / last_date /
# synced_at / row_count) instead of v2's generic (key / value / synced_at).
# The DROP TABLE IF EXISTS sync_state before CREATE ensures old v1 DBs
# (which may have a different shape) get migrated cleanly. CREATE TABLE
# IF NOT EXISTS alone would not update an existing table's columns.
SCHEMA_SQL = """
DROP TABLE IF EXISTS sync_state;

CREATE TABLE IF NOT EXISTS series_observations (
    series_code     INTEGER NOT NULL,
    ref_date        TEXT NOT NULL,        -- YYYY-MM-DD (normalized from DD/MM/YYYY)
    value           REAL,
    synced_at       TEXT,
    PRIMARY KEY (series_code, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_code ON series_observations(series_code);
CREATE INDEX IF NOT EXISTS idx_obs_date ON series_observations(ref_date);

CREATE TABLE IF NOT EXISTS series_catalog (
    code            INTEGER PRIMARY KEY,
    name            TEXT,
    frequency       TEXT,
    unit            TEXT,
    category        TEXT,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    series_code     TEXT PRIMARY KEY,     -- e.g. "11" or "11:2024-01-01:2024-12-31"
    last_date       TEXT,                 -- most recent ref_date synced
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


def bcb_data_dir():
    """Return the BCB data directory (creates it if missing)."""
    from pathlib import Path
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None
    if memory_root:
        d = Path(memory_root) / "bcb"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "bcb"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path():
    """Return the path to sgs.db."""
    return bcb_data_dir() / "sgs.db"


def connect(read_only: bool = True):
    """Open a connection to sgs.db.

    read_only=True uses the SQLite URI mode=ro (fails if DB missing).
    read_only=False opens (or creates) the DB for writes.
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"SGS database not found at {path}. Run sync first."
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
    """Create tables if they don't exist + populate series_catalog.

    [v3] The DROP TABLE IF EXISTS sync_state before CREATE ensures that
    old v1 DBs (with a different sync_state shape) are migrated to the
    new schema. This runs every time ensure_schema is called, but since
    the table is empty before the first sync, the DROP is a no-op on
    fresh DBs and a one-time migration on old v1 DBs.
    """
    conn.executescript(SCHEMA_SQL)
    # Populate catalog (INSERT OR REPLACE so re-syncs update metadata).
    rows = [
        (code, meta[0], meta[1], meta[2], meta[3], meta[4])
        for code, meta in SERIES_CATALOG.items()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO series_catalog "
        "(code, name, frequency, unit, category, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def series_url(code: int) -> str:
    """Build the JSON data endpoint URL for a series."""
    return f"{API_BASE}/bcdata.sgs.{code}/dados"


def series_last_url(code: int, n: int = 1) -> str:
    """Build the ultimos/N (last-N) endpoint URL for a series."""
    return f"{API_BASE}/bcdata.sgs.{code}/dados/ultimos/{n}"
