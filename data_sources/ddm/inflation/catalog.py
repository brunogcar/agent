"""data_sources/ddm/inflation/catalog.py -- Schema + index catalog for DDM Inflation.

DDM Inflation = Brazilian inflation indices scraped from dadosdemercado.com.br.
Each index has its own page at /indices/{slug} with 2 HTML tables:
  1. Monthly matrix  (id="index-values")  -- year rows, Jan-Dez + Ano columns
  2. Historical monthly (class "normal-table") -- DESC monthly rows with
     month_value / year_acumulado / acumulado_12m

Storage: memory_db/ddm/inflation.db (per-subdomain DB in the DDM base folder)
the bcb/focus pattern of one DB per subdomain).

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + INDEX_CATALOG + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Curated catalog of 3 inflation indices.
# Tuple shape: (name, category, description, unit)
#   category is always "Inflacao" for this subdomain (kept for parity with
#   the bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is always "%" (these are all percent variations).
INDEX_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "igp-m": ("IGP-M", "Inflacao",
              "Indice Geral de Precos - Mercado (FGV). Variacao mensal %.",
              "%"),
    "ipca":  ("IPCA",  "Inflacao",
              "Indice Nacional de Precos ao Consumidor Amplo (IBGE). "
              "Variacao mensal %.",
              "%"),
    "inpc":  ("INPC",  "Inflacao",
              "Indice Nacional de Precos ao Consumidor (IBGE). "
              "Variacao mensal %.",
              "%"),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (DDM pages use 'Jul/2026' strings).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS index_observations (
    slug            TEXT NOT NULL,
    ref_date        TEXT NOT NULL,        -- YYYY-MM (normalized from 'Jul/2026')
    month_value     REAL,                 -- variacao no mes (%)
    year_acumulado  REAL,                 -- acumulado no ano (%)
    acumulado_12m   REAL,                 -- acumulado 12 meses (%)
    synced_at       TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON index_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON index_observations(ref_date);

CREATE TABLE IF NOT EXISTS index_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "igp-m"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


class _Catalog(BaseDDMCatalog):
    """Inflation-specific catalog config (DB_FILENAME, schema, INDEX_CATALOG)."""

    DB_FILENAME = "inflation.db"
    SOURCE_NAME = "inflation"
    SCHEMA_SQL = SCHEMA_SQL
    INDEX_CATALOG = INDEX_CATALOG
    CATALOG_TABLE = "index_catalog"


# Re-export as module-level callables for backward compatibility.
# (sync_engine.py, status_reporter.py, query_engine.py, and
# skills/_freshness.py all import `connect`, `db_path`, `ensure_schema`.)
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
