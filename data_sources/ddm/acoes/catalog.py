"""data_sources/ddm/acoes/catalog.py -- Schema + URL helpers for DDM Acoes.

DDM Acoes = Brazilian B3 tradable stocks scraped from dadosdemercado.com.br.
The /acoes page exposes a single HTML table (id="stocks") with 5 columns:
  - Ticker   | Nome     | Negocios      | Ultima (R$) | Variacao
  - 'PETR4'  | 'Petrobras' | '52.792.400' | '44,30'   | '+2,78%'

Unlike the other DDM sub-domains (inflation/juros/poupanca), acoes has NO
INDEX_CATALOG: there is only ONE page (/acoes), and the table is a flat
list of stocks (not a per-index historical series).

Storage: memory_db/ddm/acoes.db (per-subdomain DB in the DDM base folder,
mirroring ddm/juros.db + ddm/poupanca.db side-by-side layout).

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + ACOES_PATH + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Canonical URL for the acoes page. No slug substitution (single page).
ACOES_PATH = "/acoes"


# Schema: one table per subdomain. Each row is a stock snapshot keyed by
# ticker (PK). Re-syncing replaces the entire snapshot (INSERT OR REPLACE).
#
# ref_date is the YYYY-MM-DD of the data (the day the snapshot was scraped -
# DDM does not expose a "data do pregao" column on the acoes page itself,
# so we use the scrape date as a proxy).
#
# [v2] stocks_history — the EVOLUTION store. The DDM /acoes page is a LIVE
# quote table: unlike inflation/juros/poupanca (whose pages carry full
# historical series), acoes ships NO history — so the only way to answer
# "how did the price distribution move over time?" is to ACCUMULATE one
# snapshot per sync ourselves. Every sync_all() appends the day's rows
# keyed by (ref_date, ticker) — re-syncing the same day replaces that
# day's snapshot (idempotent), a sync on a new day ADDS one. The table
# starts empty on pre-v2 DBs (CREATE TABLE IF NOT EXISTS is the whole
# migration) and the first post-upgrade sync also preserves the previous
# `stocks` snapshot into it (see sync_engine.py), so the evolution starts
# with data the user already has instead of from zero.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker        TEXT PRIMARY KEY,     -- 'PETR4'
    name          TEXT,                 -- 'Petrobras'
    negocios      INTEGER,              -- 52792400 (number of trades)
    last_price    REAL,                 -- 44.30 (BRL)
    variation     REAL,                 -- 2.78 (percentage, can be negative)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    ref_date      TEXT                  -- YYYY-MM-DD (scrape date)
);

CREATE INDEX IF NOT EXISTS idx_stocks_negocios  ON stocks(negocios);
CREATE INDEX IF NOT EXISTS idx_stocks_price     ON stocks(last_price);
CREATE INDEX IF NOT EXISTS idx_stocks_variation ON stocks(variation);

CREATE TABLE IF NOT EXISTS stocks_history (
    ref_date      TEXT NOT NULL,        -- YYYY-MM-DD (snapshot date)
    ticker        TEXT NOT NULL,        -- 'PETR4'
    name          TEXT,                 -- 'Petrobras'
    negocios      INTEGER,              -- 52792400 (number of trades)
    last_price    REAL,                 -- 44.30 (BRL)
    variation     REAL,                 -- 2.78 (percentage, can be negative)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    PRIMARY KEY (ref_date, ticker)      -- one row per ticker per day
);

CREATE INDEX IF NOT EXISTS idx_stocks_history_date ON stocks_history(ref_date);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'acoes' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
"""


class _Catalog(BaseDDMCatalog):
    """Acoes-specific catalog config (DB_FILENAME, schema; no INDEX_CATALOG)."""

    DB_FILENAME = "acoes.db"
    SOURCE_NAME = "acoes"
    SCHEMA_SQL = SCHEMA_SQL
    # Single-page source: no INDEX_CATALOG, no CATALOG_TABLE.
    INDEX_CATALOG = {}
    CATALOG_TABLE = ""


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def acoes_url() -> str:
    """Build the full URL for the acoes page."""
    return f"{API_BASE}{ACOES_PATH}"
