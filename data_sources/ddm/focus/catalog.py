"""data_sources/ddm/focus/catalog.py -- Schema + URL helpers for DDM Focus.

DDM Focus = Brazilian Boletim Focus (market expectations survey) scraped from
dadosdemercado.com.br/boletim-focus. The page exposes 4 yearly tables (one
per target year: 2026, 2027, 2028, 2029), each `<table class="normal-table">`
with the same 6-column shape:

    Indicador | Ha 4 semanas | 1 sem | Hoje | Comp. | Resp.

Values are PT-BR formatted strings preserved verbatim from the source:
    - "5,151%"      -- percent with comma decimal
    - "R$ 5,200"    -- currency with PT-BR thousands + decimal
    - "149"         -- respondent count (integer)
    - Comp. column  -- one of three glyphs: up/down/flat

Unlike the other DDM sub-domains (inflation / juros / poupanca / acoes),
Focus is a single-page snapshot, not a per-index historical series. There
is NO catalog of indices: the 4 year-tables each carry 12-13 indicator
rows (IPCA, PIB Total, Cambio, Selic, etc.) which are discovered at parse
time. The DB stores each (year, indicator, ref_date) combination so a
history of focus snapshots is preserved across syncs.

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
# All numeric values are stored as TEXT strings preserving the source format
# ("5,151%", "R$ 5,200"). Downstream consumers (charts, KPIs) parse the
# strings into floats on demand. This mirrors the acoes variation-pattern
# but is even more permissive: Focus mixes percentage, currency, and
# integer-count columns in the same snapshot, so keeping the original
# string form avoids lossy conversions.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS focus_observations (
    year            INTEGER NOT NULL,
    indicator       TEXT NOT NULL,
    four_weeks_ago  TEXT,
    one_week_ago    TEXT,
    today           TEXT,
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
