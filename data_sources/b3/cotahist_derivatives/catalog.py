"""data_sources/b3/cotahist_derivatives/catalog.py -- Schema + BDI filter + ticker parser.

Derivatives data from COTAHIST: options (calls/puts), term, forward.
Stored in the SAME cotahist.db as a separate `cotahist_derivatives` table.

BDI codes (verified from B3's official COTAHIST layout PDF):
  78 = CALL OPTIONS (stock)
  82 = PUT OPTIONS (stock)
  83 = INDEX CALL OPTIONS
  84 = INDEX PUT OPTIONS
  26 = TERM (forward contracts)

Market types (TPMERC):
  060 = CALL OPTIONS
  070 = PUT OPTIONS
  013 = TERM
  017 = FORWARD WITH GAIN RETENTION
  020 = FORWARD WITH CONTINUOUS MOVEMENT

Option ticker format: UNDERLYING + MONTH_CODE + STRIKE
  Call month codes: A=Jan, B=Feb, ..., L=Dec
  Put month codes:  M=Jan, N=Feb, ..., X=Dec
  Examples: PETRH36 = PETR call Aug strike 36
            PETRT36 = PETR put Aug strike 36
"""
from __future__ import annotations

from pathlib import Path


# ── BDI codes for derivatives ────────────────────────────────────────────────

# [v1.1] Expanded to ALL derivative BDI codes — options, exercise, term, forward.
# This is the FINAL structural change. After the initial full re-sync, only
# incremental updates (sync(year=current, force=True)) are needed.
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

# Market type codes for derivatives.
DERIVATIVES_MARKET_TYPES = {13, 17, 20, 60, 70}

# BDI code → human-readable type.
BDI_LABELS = {
    # Options
    78: "CALL",
    82: "PUT",
    83: "CALL (index)",
    84: "PUT (index)",
    # Exercise of options
    38: "EXERCISE CALL",
    42: "EXERCISE PUT",
    22: "EXERCISE CALL (index)",
    32: "EXERCISE PUT (index)",
    # Term
    26: "TERM",
    74: "TERM",
    # Forward
    46: "FORWARD",
    48: "FORWARD",
}

# [v1.1] BDI code → derivative type category.
# Used to populate the `derivative_type` column during sync.
BDI_TO_DERIVATIVE_TYPE = {
    # Options
    78: "OPTION", 82: "OPTION", 83: "OPTION", 84: "OPTION",
    # Exercise of options
    38: "EXERCISE", 42: "EXERCISE", 22: "EXERCISE", 32: "EXERCISE",
    # Term
    26: "TERM", 74: "TERM",
    # Forward
    46: "FORWARD", 48: "FORWARD",
}

# BDI codes for stock options exercise (used by the options skill v1.1).
STOCK_EXERCISE_BDI = {38, 42}


# ── Option ticker parser ────────────────────────────────────────────────────

# Call month codes (A-L = January-December).
_CALL_MONTHS = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6,
    "G": 7, "H": 8, "I": 9, "J": 10, "K": 11, "L": 12,
}

# Put month codes (M-X = January-December).
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
    underlying. This avoids false matches when underlying letters (e.g. 'R'
    in "PETR") overlap with month code letters.

    Examples:
      PETRH36  → {underlying: "PETR", type: "CALL", month: 8, strike: 36.0}
      PETRT36  → {underlying: "PETR", type: "PUT",  month: 8, strike: 36.0}
      PETRA215 → {underlying: "PETR", type: "CALL", month: 1, strike: 21.5}

    Returns None if the ticker doesn't match the option pattern.
    """
    if not symbol or len(symbol) < 5:
        return None

    s = symbol.strip().upper()

    # Find where the trailing digits start (the strike).
    digit_start = len(s)
    while digit_start > 0 and s[digit_start - 1].isdigit():
        digit_start -= 1

    if digit_start == len(s):
        return None  # No trailing digits → not an option ticker

    # The character just before the digits is the month code.
    month_pos = digit_start - 1
    month_char = s[month_pos]

    if month_char in _CALL_MONTHS:
        opt_type = "CALL"
        month = _CALL_MONTHS[month_char]
    elif month_char in _PUT_MONTHS:
        opt_type = "PUT"
        month = _PUT_MONTHS[month_char]
    else:
        return None  # Not a valid month code

    underlying = s[:month_pos]
    strike_str = s[month_pos + 1:]

    if not underlying or not strike_str:
        return None

    # Parse strike: digits may end in "5" meaning half.
    try:
        strike_raw = int(strike_str)
    except ValueError:
        return None

    # B3 convention: last digit "5" = half.
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


# ── Schema ───────────────────────────────────────────────────────────────────

# Same columns as cotahist + derived columns from ticker parsing.
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
    -- Derived columns (parsed from ticker during sync).
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


def db_path() -> Path:
    """Return path to cotahist.db (same DB as equities — shared)."""
    try:
        from data_sources.b3.cotahist.catalog import db_path as _cotahist_db_path
        return _cotahist_db_path()
    except Exception:
        from core.config import cfg
        d = Path(getattr(cfg, "memory_root", Path.cwd())) / "b3"
        d.mkdir(parents=True, exist_ok=True)
        return d / "cotahist.db"


def connect(read_only: bool = True):
    """Connect to cotahist.db (shared with equities table)."""
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"cotahist.db not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{path}?mode=ro" if read_only else str(path),
                           uri=read_only)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn) -> None:
    """Create the derivatives table if it doesn't exist.

    [v3] Also migrates an existing table: if the `regtype` column is missing
    (created by v1 before the fix), ALTER TABLE adds it. This allows re-syncing
    without deleting the DB.
    """
    conn.executescript(DERIVATIVES_SCHEMA_SQL)

    # [v3] Migration: check if regtype column exists, add if missing.
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
    # [v1.1] Create the derivative_type index if it doesn't exist.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deriv_type ON cotahist_derivatives(derivative_type)")

    conn.commit()
