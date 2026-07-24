"""data_sources/b3/brapi/catalog.py -- Schema constants for brapi.dev sub-domain.

brapi.dev is a Brazilian-market REST API aggregator. Free tier covers
PETR4, VALE3, ITUB4, MGLU3 without token. Full coverage with free signup.

API: https://brapi.dev/api/
  /quote/{ticker}              — current price + market cap + P/E + EPS
  /quote/{ticker}?range=1y&interval=1d — historical OHLCV
  /available                   — full ticker list (1,796 tickers in 1 call)

Storage: memory_db/b3/brapi.db (quotes + tickers)
"""

from __future__ import annotations

API_BASE = "https://brapi.dev/api"

# Free tier tickers (no token needed)
FREE_TICKERS = ["PETR4", "VALE3", "ITUB4", "MGLU3"]

# Valid ranges for historical OHLCV
VALID_RANGES = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
VALID_INTERVALS = ["1d", "5d", "1wk", "1mo", "3mo"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickers (
    symbol      TEXT PRIMARY KEY,
    synced_at   TEXT
);

CREATE TABLE IF NOT EXISTS quotes (
    symbol              TEXT NOT NULL,
    date                TEXT NOT NULL,   -- YYYY-MM-DD (converted from epoch)
    open                REAL,
    high                REAL,
    low                 REAL,
    close               REAL,
    adjusted_close      REAL,
    volume              INTEGER,
    synced_at           TEXT,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_quotes_symbol ON quotes(symbol);
CREATE INDEX IF NOT EXISTS idx_quotes_date ON quotes(date);

CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    synced_at   TEXT
);
"""


def b3_data_dir():
    """Return the B3 data directory."""
    from core.config import cfg
    from pathlib import Path
    memory_root = getattr(cfg, "memory_root", None)
    if memory_root:
        d = Path(memory_root) / "b3"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path.cwd() / "memory_db" / "b3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path():
    """Return the path to brapi.db."""
    return b3_data_dir() / "brapi.db"


def connect(read_only: bool = True):
    """Open a connection to brapi.db."""
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"Brapi database not found at {path}. Run sync first."
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
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
