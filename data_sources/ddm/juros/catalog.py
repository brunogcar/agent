"""data_sources/ddm/juros/catalog.py -- Schema + index catalog for DDM Juros.

DDM Juros = Brazilian interest-rate indices scraped from dadosdemercado.com.br.
Each index has its own page at /indices/{slug} with ONLY 1 HTML table:
  1. Monthly matrix  (id="index-values")  -- year rows, Jan-Dez columns only
                                              (NO "Ano" acumulado column).

There is NO historical table on these pages. The historical series is
DERIVED from the matrix at fetch-time (see fetcher.flatten_matrix_to_observations):
  - month_value   = cell value (daily rate %)
  - media_no_ano  = AVERAGE of all months in same year UP TO that month
  - media_12m     = AVERAGE of the last 12 months (rolling)

Storage: memory_db/ddm/juros.db (per-subdomain DB, mirrors the bcb/focus
pattern of one DB per subdomain. Sits alongside inflation.db in the
shared memory_db/ddm/ folder.)

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + JUROS_CATALOG + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Curated catalog of 3 juros indices.
# Tuple shape: (name, category, description, unit)
#   category is always "Juros" for this subdomain (kept for parity with
#   the bcb/sgs catalog shape and to allow future cross-subdomain filtering).
#   unit is always "% a.a." (annual rate - these are daily rates quoted as
#   annualized %).
JUROS_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "selic":      ("Selic",      "Juros",
                   "Taxa Selic diaria (BCB). Taxa media ajustada dos bancos "
                   "no SELIC, % a.a.",
                   "% a.a."),
    "meta-selic": ("Meta Selic", "Juros",
                   "Meta para a taxa Selic definida pelo Copom (Comite de "
                   "Politica Monetaria), % a.a.",
                   "% a.a."),
    "cdi":        ("CDI",        "Juros",
                   "Certificado de Deposito Interbancario. Taxa media dos "
                   "financiamentos diarios no mercado interbank, % a.a.",
                   "% a.a."),
}

# Schema: one table per subdomain. Each observation is a monthly row keyed
# by (slug, ref_date) where ref_date is normalized to 'YYYY-MM' at the
# fetcher boundary (the matrix cells are keyed by year + Portuguese month
# label like 'Jul').
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS juros_observations (
    slug          TEXT NOT NULL,
    ref_date      TEXT NOT NULL,        -- YYYY-MM (derived from matrix cell)
    month_value   REAL,                 -- daily rate (% a.a.)
    media_no_ano  REAL,                 -- year-to-date average (% a.a.)
    media_12m     REAL,                 -- rolling 12-month average (% a.a.)
    synced_at     TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_obs_slug ON juros_observations(slug);
CREATE INDEX IF NOT EXISTS idx_obs_date ON juros_observations(ref_date);

CREATE TABLE IF NOT EXISTS juros_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "selic"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
"""


class _Catalog(BaseDDMCatalog):
    """Juros-specific catalog config (DB_FILENAME, schema, JUROS_CATALOG)."""

    DB_FILENAME = "juros.db"
    SOURCE_NAME = "juros"
    SCHEMA_SQL = SCHEMA_SQL
    INDEX_CATALOG = JUROS_CATALOG
    CATALOG_TABLE = "juros_catalog"


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def index_url(slug: str) -> str:
    """Build the full URL for an index page."""
    return f"{API_BASE}/indices/{slug}"
