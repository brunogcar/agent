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
    """Return the B3 data directory.

    [Phase 4 C4] Delegates to data_sources._base.catalog.data_dir("b3").
    Byte-for-byte identical to b3/cotahist/catalog.py:b3_data_dir and
    b3/api/catalog.py:b3_data_dir before this commit (now all 3 delegate
    to _base).
    """
    from data_sources._base.catalog import data_dir
    return data_dir("b3")


def db_path():
    """Return the path to brapi.db."""
    return b3_data_dir() / "brapi.db"


def connect(read_only: bool = True):
    """Open a connection to brapi.db.

    [Phase 4 C4] Delegates to data_sources._base.catalog.connect. Error
    message preserved exactly by passing source_name="Brapi".
    """
    from data_sources._base.catalog import connect as _base_connect
    return _base_connect(db_path(), "Brapi", read_only)


def ensure_schema(conn):
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
