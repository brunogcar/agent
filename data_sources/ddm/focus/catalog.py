"""data_sources/ddm/focus/catalog.py -- Schema + URL helpers for DDM Focus.

DDM Focus = Brazilian Boletim Focus (market expectations survey) scraped from
dadosdemercado.com.br/boletim-focus. The page exposes 4 yearly tables (one
per target year: 2026, 2027, 2028, 2029), each `<table class="normal-table">`
with the same 6-column shape:

    Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.

[v2] Values are now stored as REAL (float), not TEXT. The fetcher parses
PT-BR strings ("5,151%", "R$ 5,200") at fetch time using the shared
parse_br_number / parse_brl helpers. This enables numeric SQL operations
(sorting, aggregation, charting) and eliminates the need for display-layer
parsing on every query.

Storage: memory_db/ddm/focus.db (per-subdomain DB in the DDM base folder,
mirroring ddm/acoes.db + ddm/juros.db + ddm/poupanca.db side-by-side layout).

[Phase 3, Commit 1] Refactored to inherit from `data_sources/ddm/_base/`
(BaseDDMCatalog). The shared ddm_data_dir() / connect() / ensure_schema()
scaffold now lives in _base/catalog_base.py; this module keeps only the
source-specific SCHEMA_SQL + FOCUS_URL + URL helper.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

# Canonical URL for the Boletim Focus page. Single page, no slug substitution.
FOCUS_URL = f"{API_BASE}/boletim-focus"


# Schema: focus_observations holds one row per (year, indicator, ref_date).
# ref_date is the YYYY-MM-DD of the sync (Focus is weekly; DDM does not
# expose a publication-date column on the page itself, so the sync date is
# the closest proxy for the bulletin's reference week).
#
# [v2] Numeric values stored as REAL (float), not TEXT. The fetcher parses
# PT-BR strings at fetch time. comparison stays TEXT (categorical: up/down/flat).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS focus_observations (
    year            INTEGER NOT NULL,
    indicator       TEXT NOT NULL,
    four_weeks_ago  REAL,
    one_week_ago    REAL,
    today           REAL,
    comparison      TEXT,
    respondents     INTEGER,
    ref_date        TEXT,
    synced_at       TEXT,
    PRIMARY KEY (year, indicator, ref_date)
);

CREATE INDEX IF NOT EXISTS idx_focus_year      ON focus_observations(year);
CREATE INDEX IF NOT EXISTS idx_focus_indicator ON focus_observations(indicator);
CREATE INDEX IF NOT EXISTS idx_focus_ref_date  ON focus_observations(ref_date);

CREATE TABLE IF NOT EXISTS sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'focus' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
"""

# [v2] Migration SQL: converts TEXT columns to REAL by casting existing data.
# Runs once on sync if the DB has the old TEXT schema (detected by checking
# column type). SQLite doesn't support ALTER COLUMN, so we use the
# CREATE-new + INSERT-with-cast + DROP + RENAME pattern.
MIGRATION_SQL = """
-- Migration from TEXT to REAL for numeric columns.
-- Only runs if the old TEXT schema is detected (see _needs_migration()).
CREATE TABLE IF NOT EXISTS focus_observations_new (
    year            INTEGER NOT NULL,
    indicator       TEXT NOT NULL,
    four_weeks_ago  REAL,
    one_week_ago    REAL,
    today           REAL,
    comparison      TEXT,
    respondents     INTEGER,
    ref_date        TEXT,
    synced_at       TEXT,
    PRIMARY KEY (year, indicator, ref_date)
);

INSERT OR REPLACE INTO focus_observations_new
    (year, indicator, four_weeks_ago, one_week_ago, today,
     comparison, respondents, ref_date, synced_at)
SELECT
    year, indicator,
    CASE WHEN four_weeks_ago IS NULL OR four_weeks_ago = '' THEN NULL
         ELSE CAST(four_weeks_ago AS REAL) END,
    CASE WHEN one_week_ago IS NULL OR one_week_ago = '' THEN NULL
         ELSE CAST(one_week_ago AS REAL) END,
    CASE WHEN today IS NULL OR today = '' THEN NULL
         ELSE CAST(today AS REAL) END,
    comparison, respondents, ref_date, synced_at
FROM focus_observations;

DROP TABLE focus_observations;
ALTER TABLE focus_observations_new RENAME TO focus_observations;

CREATE INDEX IF NOT EXISTS idx_focus_year      ON focus_observations(year);
CREATE INDEX IF NOT EXISTS idx_focus_indicator ON focus_observations(indicator);
CREATE INDEX IF NOT EXISTS idx_focus_ref_date  ON focus_observations(ref_date);
"""


class _Catalog(BaseDDMCatalog):
    """Focus-specific catalog config (DB_FILENAME, schema; no INDEX_CATALOG)."""

    DB_FILENAME = "focus.db"
    SOURCE_NAME = "focus"
    SCHEMA_SQL = SCHEMA_SQL
    # Single-page source: no INDEX_CATALOG, no CATALOG_TABLE.
    INDEX_CATALOG = {}
    CATALOG_TABLE = ""


# Re-export as module-level callables for backward compatibility.
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema


def focus_url() -> str:
    """Return the canonical Boletim Focus URL."""
    return FOCUS_URL
