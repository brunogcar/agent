"""data_sources/ddm/fluxo/catalog.py -- Schema + URL helpers for DDM Fluxo.

DDM Fluxo = Brazilian B3 investment flow (daily net inflow / outflow by
investor type) scraped from dadosdemercado.com.br/fluxo. The page exposes
1 table: `<table class="normal-table">` with 6 columns:

    Data | Estrangeiro | Institucional | Pessoa fisica |
    Inst. Financeira | Outros

~247 data rows (daily data, ~1 year of trading days). Dates are DD/MM/YYYY
DESC (newest first). Values are PT-BR formatted strings with the "mi"
suffix (millions of R$).

Unlike ddm/focus (which stores PT-BR strings verbatim), the fluxo sub-
domain NORMALIZES values to REAL at the fetcher boundary (float in
millions of R$). This is because every column has the same unit (R$
millions) so there is no information loss; and downstream chart + table
builders benefit from clean numeric values (sortability, arithmetic for
cumulative monthly/annual views).

Storage: memory_db/ddm/fluxo.db (per-subdomain DB in the DDM base folder,
mirroring ddm/focus.db + ddm/acoes.db + ddm/juros.db + ddm/poupanca.db +
ddm/inflation/inflation.db side-by-side layout).

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + FLUXO_URL + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Canonical URL for the Fluxo page. Single page, no slug substitution.
FLUXO_URL = f"{API_BASE}/fluxo"


# Schema: fluxo_observations holds one row per ref_date (daily granularity,
# ~1 year of trading days = ~247 rows).
#
# All numeric values are stored as REAL (float in millions of R$). The
# fetcher parses PT-BR formatted strings ("1.582,35 mi") to floats at the
# boundary:
#   -1.582,35 mi  ->  -1582.35
#    1.029,81 mi  ->   1029.81
#       42,36 mi  ->     42.36
#       -9,31 mi  ->     -9.31
#
# ref_date is YYYY-MM-DD (normalized from DD/MM/YYYY at parse time).
# synced_at is the ISO timestamp of the sync (when the row was written).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fluxo_observations (
    ref_date        TEXT NOT NULL,
    estrangeiro     REAL,
    institucional   REAL,
    pessoa_fisica   REAL,
    inst_financeira REAL,
    outros          REAL,
    synced_at       TEXT,
    PRIMARY KEY (ref_date)
);

CREATE INDEX IF NOT EXISTS idx_fluxo_ref_date ON fluxo_observations(ref_date);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'fluxo' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
"""


class _Catalog(BaseDDMCatalog):
    """Fluxo-specific catalog config (DB_FILENAME, schema; no INDEX_CATALOG)."""

    DB_FILENAME = "fluxo.db"
    SOURCE_NAME = "fluxo"
    SCHEMA_SQL = SCHEMA_SQL
    # Single-page source: no INDEX_CATALOG, no CATALOG_TABLE.
    INDEX_CATALOG = {}
    CATALOG_TABLE = ""


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def fluxo_url() -> str:
    """Return the canonical Fluxo URL."""
    return FLUXO_URL
