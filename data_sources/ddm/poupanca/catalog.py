"""data_sources/ddm/poupanca/catalog.py -- Schema + index catalog for DDM Poupanca.

DDM Poupanca = Brazilian savings-account monthly yield scraped from
dadosdemercado.com.br. The poupanca page has ONLY 1 HTML table (the monthly
matrix - id="index-values") with 12 month columns (Jan..Dez) and NO "Ano"
acumulado column.

There is NO historical table on the page. The historical series is
DERIVED from the matrix at fetch-time (see fetcher.flatten_matrix_to_observations):
  - month_value        = cell value (monthly yield %)
  - acumulado_no_ano   = SUM of all months in same year UP TO that month
                         (year-to-date cumulative return)
  - acumulado_12m      = SUM of the last 12 months (rolling cumulative return)

IMPORTANT: Poupanca uses SUM (not AVERAGE like juros) because the monthly
yield is already a percentage return - summing them produces the cumulative
return. This matches the analyst's Google Sheet layout.

Storage: memory_db/ddm/poupanca.db (per-subdomain DB, mirrors the juros +
inflation pattern of one DB per subdomain. Sits alongside inflation.db +
juros.db in the shared memory_db/ddm/ folder.)

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + POUPANCA_CATALOG + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Curated catalog of 1 poupanca index.
# Tuple shape: (name, category, description, unit)
#   category is "Renda Fixa" for this subdomain (kept for parity with the
#   bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is "%" (monthly yield %).
POUPANCA_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "poupanca": ("Poupanca", "Renda Fixa",
                 "Poupanca - rendimento mensal. Taxa de rendimento da caderneta "
                 "de poupanca no mes (%).",
                 "%"),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (the matrix cells are keyed by year + Portuguese month
# label like 'Jul').
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS poupanca_observations (
    slug             TEXT NOT NULL,
    ref_date         TEXT NOT NULL,        -- YYYY-MM (derived from matrix cell)
    month_value      REAL,                 -- monthly yield (%)
    acumulado_no_ano REAL,                 -- year-to-date SUM (%)
    acumulado_12m    REAL,                 -- rolling 12-month SUM (%)
    synced_at        TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON poupanca_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON poupanca_observations(ref_date);

CREATE TABLE IF NOT EXISTS poupanca_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "poupanca"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


class _Catalog(BaseDDMCatalog):
    """Poupanca-specific catalog config (DB_FILENAME, schema, POUPANCA_CATALOG)."""

    DB_FILENAME = "poupanca.db"
    SOURCE_NAME = "poupanca"
    SCHEMA_SQL = SCHEMA_SQL
    INDEX_CATALOG = POUPANCA_CATALOG
    CATALOG_TABLE = "poupanca_catalog"


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
