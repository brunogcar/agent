"""data_sources/b3/api/catalog.py -- Schema constants for B3 API sub-domain.

[v2.0] B3's paginated JSON API (20 rows/page, 2,283 pages for derivatives)
was fundamentally limited: 4 columns only, 22-minute sync time, server-side
throttling, and 504 timeouts on ~40% of pages. Replaced with the 2-step
CSV bulk download API:

  Step 1: GET /api/download/requestname?fileName={tableName}&date={date}
    → {"token": "...", "file": {"name": "...", "extension": ".csv"}}

  Step 2: GET /api/download/?token={token}
    → Full CSV file (semicolon-separated, ALL columns, ALL rows)

This reduces sync time from ~1,331s (22 min) to ~1-3s per table and
returns the full column set (17-52 columns vs the JSON API's 4).

API base: https://arquivos.b3.com.br

Tables:
  InstrumentsConsolidated          → instruments (52 cols, ~169K rows)
  TradeInformationConsolidated     → trades (15 cols, ~162K rows)
  TradeInformationConsolidatedAfterHours → after_hours (15 cols, ~630 rows)
  DerivativesOpenPosition          → derivatives (17 cols, ~46K rows)

CSV format: semicolon-separated (;), ISO-8859-1 encoding.
3 of 4 tables have a "Status do Arquivo: Final" line before the header
(derivatives does NOT — its first line IS the header).

Storage: memory_db/b3/{table}.db

FUTURE: B3 announced that the public data pages (cotações, dados públicos)
were decommissioned on 2026-03-31 and migrated to the BDI portal
(https://arquivos.b3.com.br/bdi/tabelas). The "Quadro Analítico das
Posições em Aberto" (analytical open positions table) is expected on BDI
from 2026-06-30. If the /api/download endpoint is decommissioned, the
BDI portal should be investigated as the replacement. See ChatGPT's
research from the 2026-08-24 code review.
"""

from __future__ import annotations

# ── API base ─────────────────────────────────────────────────────────────────

API_BASE = "https://arquivos.b3.com.br"
DOWNLOAD_TOKEN_URL = f"{API_BASE}/api/download/requestname"
DOWNLOAD_CSV_URL = f"{API_BASE}/api/download/"

# ── Table registry ───────────────────────────────────────────────────────────

B3_TABLES = {
    "instruments": {
        "api_name":   "InstrumentsConsolidated",
        "db_file":    "instruments.db",
        "table":      "instruments",
        "pk":         "TckrSymb",
        "description": "Master instrument reference: all listed securities with company info, segment, governance",
        "indexes":    ["TckrSymb", "ISIN", "SgmtNm", "CrpnNm"],
    },
    "trades": {
        "api_name":   "TradeInformationConsolidated",
        "db_file":    "trades.db",
        "table":      "trades",
        "pk":         None,  # composite: TckrSymb + RptDt
        "description": "Daily regular session trade stats: prices, volume, VWAP per ticker",
        "indexes":    ["TckrSymb", "ISIN", "RptDt"],
    },
    "after_hours": {
        "api_name":   "TradeInformationConsolidatedAfterHours",
        "db_file":    "after_hours.db",
        "table":      "after_hours",
        "pk":         None,
        "description": "After-hours session trade stats: same schema as trades, different session",
        "indexes":    ["TckrSymb", "RptDt"],
    },
    "derivatives": {
        "api_name":   "DerivativesOpenPosition",
        "db_file":    "derivatives.db",
        "table":      "derivatives",
        "pk":         None,
        "description": "Derivatives open interest: futures and options positions, daily variation",
        "indexes":    ["TckrSymb", "ISIN", "Asst"],
    },
}

# ── DB path ──────────────────────────────────────────────────────────────────

def b3_data_dir():
    """Return the B3 data directory.

    [Phase 4 C4] Delegates to data_sources._base.catalog.data_dir("b3").
    """
    from data_sources._base.catalog import data_dir
    return data_dir("b3")


def db_path(table_name: str):
    """Return the SQLite DB path for a table."""
    return b3_data_dir() / B3_TABLES[table_name]["db_file"]


def connect(table_name: str, read_only: bool = True):
    """Open a SQLite connection for a B3 table.

    [Phase 4 C4] Delegates to data_sources._base.catalog.connect.
    """
    from data_sources._base.catalog import connect as _base_connect
    return _base_connect(db_path(table_name), "B3", read_only)


def ensure_schema(conn, table_name: str, columns: list[str]):
    """Create table if it doesn't exist, or add missing columns via ALTER TABLE.

    [v2.0] Columns now come from the CSV header (17-52 columns) instead of
    the JSON API response (4 columns). All columns are TEXT (B3 sends
    everything as strings in the CSV).

    [v2.1 fix] If the table already exists with the old 4-column JSON API
    schema, ALTER TABLE ADD COLUMN is used to add the missing columns
    instead of failing with "no such column". This handles the migration
    from the old paginated JSON API to the new CSV bulk download.
    """
    table = B3_TABLES[table_name]["table"]

    # Check if the table already exists
    existing_cols = [
        r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    ]

    if existing_cols:
        # Table exists — check for missing columns and add them via ALTER TABLE.
        # SQLite ALTER TABLE ADD COLUMN can only add one column at a time,
        # and can't add columns that already exist.
        import re
        for col in columns:
            if col not in existing_cols:
                # [v3 fix] Sanitize column name — only allow alphanumeric + underscore.
                # B3 controls the data, but a stray character would produce a
                # confusing SQL error. (Claude 2 review finding.)
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", col):
                    _progress_msg(f"[b3_sync] WARNING: Skipping invalid column name '{col}' in {table}")
                    continue
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
                _progress_msg(f"[b3_sync] Added column '{col}' to {table} (schema migration)")
        # Also ensure _ingested_at exists
        if "_ingested_at" not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN _ingested_at TEXT")
        conn.commit()
        return

    # Table doesn't exist — create it fresh with all columns.
    col_defs = ",\n    ".join(f"{c} TEXT" for c in columns)
    col_defs += ",\n    _ingested_at TEXT"

    indexes = B3_TABLES[table_name].get("indexes", [])

    sql = f"""
    CREATE TABLE IF NOT EXISTS {table} (
        {col_defs}
    );
    """
    for idx_col in indexes:
        if idx_col in columns:
            sql += f"\n    CREATE INDEX IF NOT EXISTS idx_{table}_{idx_col} ON {table}({idx_col});"

    sql += """
    CREATE TABLE IF NOT EXISTS sync_state (
        table_name  TEXT,
        date        TEXT,
        synced_at   TEXT,
        row_count   INTEGER DEFAULT 0,
        page_count  INTEGER DEFAULT 0,
        last_page   INTEGER DEFAULT 0,
        PRIMARY KEY (table_name, date)
    );
    """
    conn.executescript(sql)
    conn.commit()


def _progress_msg(msg: str) -> None:
    """Print a progress message to stderr (used by ensure_schema for migration)."""
    import sys
    print(msg, file=sys.stderr, flush=True)
