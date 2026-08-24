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
    """Return the B3 data directory.

    [Phase 4 C4] Delegates to data_sources._base.catalog.data_dir("b3").
    Byte-for-byte identical to b3/brapi/catalog.py:b3_data_dir and
    b3/api/catalog.py:b3_data_dir before this commit (now all 3 delegate
    to _base).
    """
    from data_sources._base.catalog import data_dir
    return data_dir("b3")


def db_path():
    """Return the path to cotahist.db."""
    return b3_data_dir() / "cotahist.db"


def connect(read_only: bool = True):
    """Open a connection to cotahist.db.

    [Phase 4 C4] Delegates to data_sources._base.catalog.connect. Error
    message preserved exactly by passing source_name="COTAHIST".
    """
    from data_sources._base.catalog import connect as _base_connect
    return _base_connect(db_path(), "COTAHIST", read_only)


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


# ── Derivatives (options, exercise, term, forward) ───────────────────────────
# [v1.2] Derivatives data stored in the SAME cotahist.db as a separate
# `cotahist_derivatives` table. Populated during the same sync pass.
# All derivatives constants + functions live HERE (not in a separate sub-domain).

# BDI codes for derivatives (expanded in v1.1 to all derivative types).
DERIVATIVES_BDI_FILTER = {
    # Options (stock + index)
    78, 82,           # Stock calls / puts
    83, 84,            # Index calls / puts
    # Exercise of options (stock + index)
    38, 42,            # Exercise of stock calls / puts
    22, 32,            # Exercise of index calls / puts
    # Term (a termo)
    26, 74,            # Term contracts
    # Forward
    46, 48,            # Forward with continuous movement / gain retention
}

DERIVATIVES_MARKET_TYPES = {13, 17, 20, 60, 70}

BDI_LABELS = {
    78: "CALL", 82: "PUT", 83: "CALL (index)", 84: "PUT (index)",
    38: "EXERCISE CALL", 42: "EXERCISE PUT",
    22: "EXERCISE CALL (index)", 32: "EXERCISE PUT (index)",
    26: "TERM", 74: "TERM",
    46: "FORWARD", 48: "FORWARD",
}

BDI_TO_DERIVATIVE_TYPE = {
    78: "OPTION", 82: "OPTION", 83: "OPTION", 84: "OPTION",
    38: "EXERCISE", 42: "EXERCISE", 22: "EXERCISE", 32: "EXERCISE",
    26: "TERM", 74: "TERM",
    46: "FORWARD", 48: "FORWARD",
}

STOCK_EXERCISE_BDI = {38, 42}
TERM_BDI = {26, 74}
FORWARD_BDI = {46, 48}

# ── Option ticker parser ────────────────────────────────────────────────────

_CALL_MONTHS = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6,
    "G": 7, "H": 8, "I": 9, "J": 10, "K": 11, "L": 12,
}

_PUT_MONTHS = {
    "M": 1, "N": 2, "O": 3, "P": 4, "Q": 5, "R": 6,
    "S": 7, "T": 8, "U": 9, "V": 10, "W": 11, "X": 12,
}

_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def parse_option_ticker(symbol: str) -> dict | None:
    """Parse a B3 option ticker into its components.

    Format: UNDERLYING + MONTH_CODE + STRIKE
      - UNDERLYING: 4-5 letters (before the month code)
      - MONTH_CODE: 1 letter (A-L for calls, M-X for puts)
      - STRIKE: 2-4 digits (may end in 5 = half, e.g. "215" = 21.50)

    Parsing strategy: find trailing digits (the strike), then the character
    just before them is the month code, and everything before that is the
    underlying.
    """
    if not symbol or len(symbol) < 5:
        return None
    s = symbol.strip().upper()
    digit_start = len(s)
    while digit_start > 0 and s[digit_start - 1].isdigit():
        digit_start -= 1
    if digit_start == len(s):
        return None
    month_pos = digit_start - 1
    month_char = s[month_pos]
    if month_char in _CALL_MONTHS:
        opt_type = "CALL"
        month = _CALL_MONTHS[month_char]
    elif month_char in _PUT_MONTHS:
        opt_type = "PUT"
        month = _PUT_MONTHS[month_char]
    else:
        return None
    underlying = s[:month_pos]
    strike_str = s[month_pos + 1:]
    if not underlying or not strike_str:
        return None
    try:
        strike_raw = int(strike_str)
    except ValueError:
        return None
    if strike_raw % 10 == 5 and strike_raw > 5:
        strike = (strike_raw - 5) / 10.0 + 0.5
    else:
        strike = float(strike_raw)
    return {
        "underlying": underlying,
        "option_type": opt_type,
        "expiration_month": month,
        "expiration_month_name": _MONTH_NAMES.get(month, ""),
        "strike_parsed": strike,
    }


# ── Derivatives schema ─────────────────────────────────────────────────────

DERIVATIVES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cotahist_derivatives (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regtype         TEXT,
    refdate         TEXT NOT NULL,
    bdi_code        INTEGER,
    symbol          TEXT NOT NULL,
    market_type     INTEGER,
    corp_name       TEXT,
    spec_code       TEXT,
    days_settle     INTEGER,
    currency        TEXT,
    open            REAL,
    high            REAL,
    low             REAL,
    average         REAL,
    close           REAL,
    best_bid        REAL,
    best_ask        REAL,
    trade_count     INTEGER,
    contracts       INTEGER,
    volume          REAL,
    strike          REAL,
    strike_adj      TEXT,
    maturity        TEXT,
    lot_size        INTEGER,
    strike_pts      REAL,
    isin            TEXT,
    dist_id         INTEGER,
    underlying      TEXT,
    option_type     TEXT,
    expiration_month INTEGER,
    strike_parsed   REAL,
    derivative_type TEXT,
    _ingested_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_deriv_symbol ON cotahist_derivatives(symbol);
CREATE INDEX IF NOT EXISTS idx_deriv_refdate ON cotahist_derivatives(refdate);
CREATE INDEX IF NOT EXISTS idx_deriv_underlying ON cotahist_derivatives(underlying);
CREATE INDEX IF NOT EXISTS idx_deriv_maturity ON cotahist_derivatives(maturity);
CREATE INDEX IF NOT EXISTS idx_deriv_underlying_maturity ON cotahist_derivatives(underlying, maturity);
CREATE INDEX IF NOT EXISTS idx_deriv_type ON cotahist_derivatives(derivative_type);

CREATE TABLE IF NOT EXISTS cotahist_derivatives_sync_state (
    year        INTEGER PRIMARY KEY,
    synced_at   TEXT NOT NULL,
    rows_added  INTEGER DEFAULT 0,
    duration_s  REAL DEFAULT 0
);
"""


def ensure_derivatives_schema(conn) -> None:
    """Create the derivatives table if it doesn't exist + migrate old tables.

    Checks for missing columns (regtype, underlying, option_type,
    expiration_month, strike_parsed, derivative_type) via PRAGMA table_info
    and ALTER TABLE ADD COLUMN if missing.
    """
    conn.executescript(DERIVATIVES_SCHEMA_SQL)

    # Check if table exists
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cotahist_derivatives'"
    ).fetchone()
    if not table_exists:
        return

    cols = {row[1] for row in conn.execute("PRAGMA table_info(cotahist_derivatives)").fetchall()}
    if "regtype" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN regtype TEXT")
    if "underlying" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN underlying TEXT")
    if "option_type" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN option_type TEXT")
    if "expiration_month" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN expiration_month INTEGER")
    if "strike_parsed" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN strike_parsed REAL")
    if "derivative_type" not in cols:
        conn.execute("ALTER TABLE cotahist_derivatives ADD COLUMN derivative_type TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deriv_type ON cotahist_derivatives(derivative_type)")
    conn.commit()
