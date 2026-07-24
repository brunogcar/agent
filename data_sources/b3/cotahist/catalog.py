"""data_sources/b3/cotahist/catalog.py -- Schema constants for COTAHIST sub-domain.

COTAHIST = B3's official historical trade data. Annual ZIP files contain
every trade for every B3-listed security (stocks, bonds, funds, options, FIIs).

Source: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP
Format: Fixed-width text (245 bytes/record), latin1 encoding, inside ZIP
Size: ~87MB ZIP → ~765MB TXT per year

Layout spec: https://www.b3.com.br/data/files/65/50/AD/26/29C8B51095EE46B5790D8AA8/HistoricalQuotations_B3.pdf

Storage: memory_db/b3/cotahist.db
"""

from __future__ import annotations


# ── URL ──────────────────────────────────────────────────────────────────────

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"
FIRST_YEAR = 2010  # Match CVM DFP start year — no need to go earlier
CSV_ENCODING = "latin-1"  # COTAHIST uses latin1

# [v1.0.1] BDI codes to keep during sync (filter out options/bonds/warrants).
# 02 = Lote Padrão (equities), 12 = Fundos Imobiliários (FIIs),
# 14 = Certificado de Investimento Coletivo, 96 = Fracionário
# This reduces the DB from ~5.7GB to ~1-2GB by dropping ~85% of rows.
BDI_FILTER = {2, 12, 14, 96}


# ── Fixed-width column layout ────────────────────────────────────────────────
# (col_name, type, start_pos_1based, end_pos_1based, description)
# B3 uses 1-based positions; Python slicing is 0-based (handled in parser)

COTAHIST_LAYOUT: list[tuple[str, str, int, int, str]] = [
    ("regtype",      "text", 1,   2,   "Record type: 00=header, 01=daily quote (trade), 99=trailer"),
    ("refdate",      "text", 3,   10,  "Trade date YYYYMMDD"),
    ("bdi_code",     "int",  11,  12,  "BDI market segment code"),
    ("symbol",       "text", 13,  24,  "Ticker symbol (e.g. PETR4, VALE3)"),
    ("market_type",  "int",  25,  27,  "Market type code (10=spot, 12=fracionário, etc.)"),
    ("corp_name",    "text", 28,  39,  "Corporation name abbreviated"),
    ("spec_code",    "text", 40,  49,  "Security specification code"),
    ("days_settle",  "int",  50,  52,  "Days to settlement (term market)"),
    ("currency",     "text", 53,  56,  "Trading currency (R$ = BRL)"),
    ("open",         "real", 57,  69,  "Opening price (implicit 2 decimals)"),
    ("high",         "real", 70,  82,  "Session high"),
    ("low",          "real", 83,  95,  "Session low"),
    ("average",      "real", 96,  108, "Volume-weighted average price"),
    ("close",        "real", 109, 121, "Closing/last trade price"),
    ("best_bid",     "real", 122, 134, "Best bid"),
    ("best_ask",     "real", 135, 147, "Best ask"),
    ("trade_count",  "int",  148, 152, "Number of trades"),
    ("contracts",    "int",  153, 170, "Total contracts/shares traded"),
    ("volume",       "real", 171, 188, "Total financial volume in BRL"),
    ("strike",       "real", 189, 201, "Strike price (options/term)"),
    ("strike_adj",   "text", 202, 202, "Strike adjustment indicator"),
    ("maturity",     "text", 203, 210, "Expiration date YYYYMMDD (derivatives)"),
    ("lot_size",     "int",  211, 217, "Standard lot size"),
    ("strike_pts",   "real", 218, 230, "Strike in points (USD options)"),
    ("isin",         "text", 231, 242, "ISIN code"),
    ("dist_id",      "int",  243, 245, "Distribution/asset version code"),
]

# Numeric columns — B3 stores without decimal point (implicit /100)
NUMERIC_COLS = {
    "open", "high", "low", "average", "close", "best_bid", "best_ask",
    "volume", "strike", "strike_pts",
}

# Integer columns — no decimal conversion
INTEGER_COLS = {
    "bdi_code", "market_type", "days_settle", "trade_count",
    "contracts", "lot_size", "dist_id",
}


# ── SQL Schema ───────────────────────────────────────────────────────────────

SCHEMA_SQL = """
DROP TABLE IF EXISTS cotahist;
CREATE TABLE cotahist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    regtype     TEXT,                   -- Record type (01=daily quote)
    refdate     TEXT NOT NULL,          -- YYYY-MM-DD (normalized from YYYYMMDD)
    symbol      TEXT NOT NULL,          -- Ticker (PETR4)
    bdi_code    INTEGER,
    market_type INTEGER,
    corp_name   TEXT,
    spec_code   TEXT,
    days_settle INTEGER,
    currency    TEXT,
    open        REAL,
    high        REAL,
    low         REAL,
    average     REAL,
    close       REAL,
    best_bid    REAL,
    best_ask    REAL,
    trade_count INTEGER,
    contracts   INTEGER,
    volume      REAL,
    strike      REAL,
    strike_adj  TEXT,
    maturity    TEXT,
    lot_size    INTEGER,
    strike_pts  REAL,
    isin        TEXT,
    dist_id     INTEGER,
    _ingested_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cotahist_symbol ON cotahist(symbol);
CREATE INDEX IF NOT EXISTS idx_cotahist_refdate ON cotahist(refdate);
CREATE INDEX IF NOT EXISTS idx_cotahist_isin ON cotahist(isin);
CREATE INDEX IF NOT EXISTS idx_cotahist_symbol_date ON cotahist(symbol, refdate);

CREATE TABLE IF NOT EXISTS sync_state (
    year        INTEGER PRIMARY KEY,
    synced_at   TEXT NOT NULL,
    rows_added  INTEGER DEFAULT 0,
    duration_s  REAL DEFAULT 0
);
"""


# ── Path + connection ────────────────────────────────────────────────────────

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
    """Return the path to cotahist.db."""
    return b3_data_dir() / "cotahist.db"


def connect(read_only: bool = True):
    """Open a connection to cotahist.db."""
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"COTAHIST database not found at {path}. Run sync first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn, recreate: bool = False):
    """Create tables + indexes if they don't exist.

    Args:
        recreate: If True, drop and recreate the cotahist table (for schema fixes).
                  WARNING: this deletes all data in the cotahist table.
    """
    if recreate:
        conn.execute("DROP TABLE IF EXISTS cotahist")

    # Check if table exists
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cotahist'"
    ).fetchone()

    if not table_exists:
        # Create fresh — use everything except the DROP
        conn.executescript(SCHEMA_SQL.replace("DROP TABLE IF EXISTS cotahist;\n", ""))
    else:
        # Check if regtype column exists (schema version check)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(cotahist)").fetchall()]
        if "regtype" not in cols:
            # Old schema — recreate
            conn.execute("DROP TABLE IF EXISTS cotahist")
            conn.executescript(SCHEMA_SQL.replace("DROP TABLE IF EXISTS cotahist;\n", ""))

    conn.commit()
