"""data_sources/cvm/bridge/catalog.py -- Schema constants for the B3-CVM bridge.

THE BRIDGE
----------
The bridge resolves B3 trading tickers (PETR4, VALE3) to CVM company identity
(CNPJ, CD_CVM, official names) so that CVM financial queries can accept a
ticker as input.

RESOLUTION CHAIN (no bulk downloads, no instruments.db dependency)
------------------------------------------------------------------
  ticker (PETR4)
    |
    v  b3/dividends per-ticker API  (already synced by data_sources.b3.dividends)
    |  dividends.company_info.code_cvm = "9512"
    v
  cd_cvm ("9512")
    |
    v  cvm/cad lookup  (cad.db, ~2677 companies, weekly CSV)
    |  cia_aberta WHERE CD_CVM='9512' -> CNPJ, names, status, sector
    v
  bridge.db ticker_map: PETR4 -> cd_cvm=9512, cnpj=33000167000101, ...

WHY NOT THE LEGACY 4-SOURCE APPROACH
------------------------------------
The legacy skills/b3/b3_cvm/ bridge joined 4 sources:
  1. instruments.db (local)  -- B3 ticker + ISIN + company info
  2. B3 ISIN ZIP (download)  -- ISIN -> CNPJ  (280k-row NUMERACA.TXT)
  3. CVM CSV (download)       -- CNPJ -> CD_CVM + names
  4. dfp_itr.db (local)       -- CNPJ -> empresa_ids

Problems with the legacy approach:
  - B3 ISIN ZIP download is fragile (CDN checks Referer/Origin, 403 without browser headers)
  - instruments.db requires a full sync (7138 pages, ~20min, often incomplete)
  - market cap (mkt_cap) came from instruments.db -- useless if sync is partial
  - 4-way join is complex and slow

The new approach replaces sources 2+3 with the dividends per-ticker API, which
returns codeCVM directly (ticker -> cd_cvm in one call). CAD provides cd_cvm ->
CNPJ + metadata. No bulk downloads, no ISIN ZIP, no instruments dependency.

SCHEMA DECISIONS
----------------
- ticker_map.ticker is PRIMARY KEY (one row per ticker).
- cd_cvm comes from the dividends API (always populated for synced tickers).
- cnpj + names + status + sector come from CAD (may be empty if cd_cvm not in
  cad.db -- e.g., very new listings or stale cad.db).
- NO mkt_cap column: market cap lives in instruments.db, which may not be fully
  synced. The bridge is for identity resolution, not market data.
- sync_log records every sync action for auditability.

Storage: memory_db/cvm/bridge.db  (co-located with dfp.db, itr.db, cad.db)
"""

from __future__ import annotations

# -- SQL schema ---------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ticker_map (
    ticker        TEXT PRIMARY KEY,   -- B3 trading symbol e.g. "PETR4"
    issuing       TEXT,               -- 4-char issuing company e.g. "PETR"
    cd_cvm        TEXT,               -- CVM code from dividends API e.g. "9512"
    trading_name  TEXT,               -- B3 trading name from dividends API
    cnpj          TEXT,               -- 14-digit CNPJ from CAD
    denom_social  TEXT,               -- official legal name from CAD
    denom_comerc  TEXT,               -- commercial name from CAD
    sit           TEXT,               -- ATIVO / CANCELADO / SUSPENSO (from CAD)
    setor_ativ    TEXT,               -- economic sector (from CAD)
    tp_merc       TEXT,               -- BOVESPA / BALCAO etc. (from CAD)
    synced_at     TEXT                -- ISO timestamp of last bridge sync
);

CREATE INDEX IF NOT EXISTS idx_bridge_cnpj   ON ticker_map(cnpj);
CREATE INDEX IF NOT EXISTS idx_bridge_cd_cvm ON ticker_map(cd_cvm);

CREATE TABLE IF NOT EXISTS sync_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at  TEXT,
    ticker     TEXT,
    action     TEXT,    -- 'linked' (success), 'no_cvm' (dividends ok but no codeCVM),
                        -- 'no_cad' (cd_cvm not in cad.db), 'error'
    cd_cvm     TEXT,
    cnpj       TEXT,
    detail     TEXT
);
"""


# -- Path + connection --------------------------------------------------------

def db_path():
    """Return the path to bridge.db (co-located with other CVM DBs)."""
    from data_sources.cvm._db import bridge_db_path
    return bridge_db_path()


def connect(read_only: bool = True):
    """Open a connection to bridge.db.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    import sqlite3
    path = db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"Bridge database not found at {path}. "
                f"Run data_source(domain='cvm', sub_domain='bridge', mode='sync', "
                f"params='{{\"ticker\":\"PETR4\"}}') first."
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
    """Create the ticker_map + sync_log tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
