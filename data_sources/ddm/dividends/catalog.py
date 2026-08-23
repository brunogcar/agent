"""data_sources/ddm/dividends/catalog.py -- Schema + URL constants for DDM Dividends.

DDM Dividends = Brazilian corporate dividend events scraped from
dadosdemercado.com.br/agenda-de-dividendos.

Single page, single table (class "normal-table"), ~200 rows.
Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento
Tipos:   Dividendo | JCP (Juros sobre Capital Proprio)

Storage: memory_db/ddm/dividends.db (per-subdomain DB, mirrors the
bcb/focus + ddm/juros + ddm/poupanca pattern of one DB per subdomain.
Sits alongside inflation.db / juros.db / poupanca.db in memory_db/ddm/.)

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + DIVIDENDS_URL + TIPOS + SORT_KEYS.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

DIVIDENDS_URL = f"{API_BASE}/agenda-de-dividendos"

# 2 tipos published by DDM in the agenda de dividendos page.
TIPOS = ("Dividendo", "JCP")

# Canonical sort keys accepted by query_engine.dividends_list.
SORT_KEYS = (
    "value", "ticker", "tipo",
    "record_date", "ex_date", "payment_date",
)

# Schema: 2 tables.
#   - dividends       : one row per (ticker, record_date, tipo) observation.
#                       Stored as REAL value + ISO date strings (YYYY-MM-DD).
#   - sync_state      : single row (slug='dividends') with last sync info.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dividends (
    ticker        TEXT NOT NULL,
    tipo          TEXT,
    value         REAL,
    record_date   TEXT,
    ex_date       TEXT,
    payment_date  TEXT,
    synced_at     TEXT,
    PRIMARY KEY (ticker, record_date, tipo)
);

CREATE INDEX IF NOT EXISTS idx_div_ticker ON dividends(ticker);
CREATE INDEX IF NOT EXISTS idx_div_record ON dividends(record_date);
CREATE INDEX IF NOT EXISTS idx_div_ex     ON dividends(ex_date);
CREATE INDEX IF NOT EXISTS idx_div_pay    ON dividends(payment_date);
CREATE INDEX IF NOT EXISTS idx_div_tipo   ON dividends(tipo);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
"""


class _Catalog(BaseDDMCatalog):
    """Dividends-specific catalog config (DB_FILENAME, schema; no INDEX_CATALOG)."""

    DB_FILENAME = "dividends.db"
    SOURCE_NAME = "dividends"
    SCHEMA_SQL = SCHEMA_SQL
    # Single-page source: no INDEX_CATALOG, no CATALOG_TABLE.
    INDEX_CATALOG = {}
    CATALOG_TABLE = ""


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema
