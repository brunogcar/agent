"""data_sources/b3/dividends/catalog.py -- Schema constants for B3 dividends.

B3 dividends/corporate actions API — per-ticker JSON, not paginated.
Returns cash dividends, stock dividends, and subscription rights.

API: https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/
      CompanyCall/GetListedSupplementCompany/{base64}
  base64 = base64({"issuingCompany":"PETR","language":"pt-br"})

Storage: memory_db/b3/dividends.db (3 tables)
"""

from __future__ import annotations

API_BASE = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS company_info (
    ticker                  TEXT PRIMARY KEY,
    issuing_company         TEXT,
    code_cvm                TEXT,
    trading_name            TEXT,
    segment                 TEXT,
    stock_capital           TEXT,
    number_common_shares    TEXT,
    number_preferred_shares TEXT,
    total_number_shares     TEXT,
    round_lot               TEXT,
    quoted_per_share_since  TEXT,
    has_common              TEXT,
    has_preferred           TEXT,
    common_shares_form      TEXT,
    preferred_shares_form   TEXT,
    _ingested_at            TEXT
);

CREATE TABLE IF NOT EXISTS cash_dividends (
    ticker          TEXT NOT NULL,
    label           TEXT,
    isin_code       TEXT NOT NULL,
    approved_on     TEXT,
    last_date_prior TEXT,
    rate            REAL,
    related_to      TEXT,
    payment_date    TEXT,
    remarks         TEXT,
    _ingested_at    TEXT
);

CREATE TABLE IF NOT EXISTS stock_dividends (
    ticker          TEXT NOT NULL,
    label           TEXT,
    isin_code       TEXT NOT NULL,
    approved_on     TEXT,
    last_date_prior TEXT,
    factor          REAL,
    asset_issued    TEXT,
    remarks         TEXT,
    _ingested_at    TEXT
);

CREATE TABLE IF NOT EXISTS subscriptions (
    ticker             TEXT NOT NULL,
    label              TEXT,
    isin_code          TEXT NOT NULL,
    approved_on        TEXT,
    last_date_prior    TEXT,
    percentage         REAL,
    asset_issued       TEXT,
    price_unit         REAL,
    subscription_date  TEXT,
    trading_period     TEXT,
    remarks            TEXT,
    _ingested_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_cash_ticker ON cash_dividends(ticker);
CREATE INDEX IF NOT EXISTS idx_cash_isin ON cash_dividends(isin_code);
CREATE INDEX IF NOT EXISTS idx_cash_approved ON cash_dividends(approved_on);
CREATE INDEX IF NOT EXISTS idx_stock_ticker ON stock_dividends(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_isin on stock_dividends(isin_code);
CREATE INDEX IF NOT EXISTS idx_sub_ticker ON subscriptions(ticker);

CREATE TABLE IF NOT EXISTS sync_state (
    ticker     TEXT PRIMARY KEY,
    synced_at  TEXT,
    cash_count INTEGER DEFAULT 0,
    stock_count INTEGER DEFAULT 0,
    sub_count  INTEGER DEFAULT 0
);
"""

def db_path():
    from core.config import cfg
    from pathlib import Path
    d = Path(getattr(cfg, "memory_root", Path.cwd())) / "b3"
    d.mkdir(parents=True, exist_ok=True)
    return d / "dividends.db"

def connect(read_only=True):
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"B3 dividends database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(f"file:{path}?mode=ro" if read_only else str(path),
                               uri=read_only)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema(conn):
    conn.executescript(SCHEMA_SQL)
    conn.commit()
