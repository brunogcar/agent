"""data_sources/b3/api/catalog.py -- Schema constants for B3 API sub-domain.

B3 migrated to a paginated JSON API (the old 3-step CSV download flow is broken).
The new API returns JSON with column metadata + values, 20 rows per page.

API: https://arquivos.b3.com.br/tabelas/table/{tableName}/{date}/{page}
  → {"name", "friendlyName", "columns": [...], "values": [[...], ...], "pageCount": N}

Tables (matching SPA URLs):
  InstrumentsConsolidated          → instruments (tickers, ISIN, company names, segment)
  TradeInformationConsolidated     → trades (daily prices, volume, VWAP)
  TradeInformationConsolidatedAfterHours → after_hours
  DerivativesOpenPosition          → derivatives

Storage: memory_db/b3/{table}.db
Encoding: JSON (API returns JSON, not CSV — no encoding issues)
"""

from __future__ import annotations

# ── API base ─────────────────────────────────────────────────────────────────

API_BASE = "https://arquivos.b3.com.br/tabelas/table"
PAGE_SIZE = 20  # B3 API returns 20 rows per page

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
        "description": "Daily regular session trade stats: prices, volume, oscillation per ticker",
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
    """Return the B3 data directory."""
    from core.config import cfg
    memory_root = getattr(cfg, "memory_root", None)
    if memory_root:
        from pathlib import Path
        d = Path(memory_root) / "b3"
        d.mkdir(parents=True, exist_ok=True)
        return d
    from pathlib import Path
    d = Path.cwd() / "memory_db" / "b3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path(table_name: str):
    """Return the SQLite DB path for a table."""
    return b3_data_dir() / B3_TABLES[table_name]["db_file"]


def connect(table_name: str, read_only: bool = True):
    """Open a SQLite connection for a B3 table."""
    import sqlite3
    path = db_path(table_name)
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"B3 database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
    else:
        if read_only:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn, table_name: str, columns: list[str]):
    """Create table if it doesn't exist, using the columns from the API response.

    B3 API returns column metadata dynamically, so we create the table
    on first sync based on what the API tells us. All columns are TEXT
    (B3 sends everything as strings in JSON values).
    """
    table = B3_TABLES[table_name]["table"]
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
        PRIMARY KEY (table_name, date)
    );
    """
    conn.executescript(sql)
    conn.commit()
