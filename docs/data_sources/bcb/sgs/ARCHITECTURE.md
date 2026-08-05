<- Back to [SGS](../SGS.md)

# 🏗️ SGS Architecture

## File Map

```text
data_sources/bcb/sgs/
├── __init__.py            # MANIFEST + route() dispatcher (8 modes)
├── catalog.py             # SERIES_CATALOG (12 series) + SCHEMA_SQL + connect/ensure_schema
├── fetcher.py             # HTTP fetcher (thread-safe, Semaphore(5), 5-min cache)
├── sync_engine.py         # sync_series / sync_all / sync_series_range
├── query_engine.py        # series / last_value / range_query / search / summary
└── status_reporter.py     # status() — DB stats
```

---

## Schema (3 tables)

```sql
-- Observations: one row per (series_code, ref_date). Composite PK = idempotent sync.
CREATE TABLE series_observations (
    series_code     INTEGER NOT NULL,
    ref_date        TEXT NOT NULL,        -- YYYY-MM-DD (normalized from DD/MM/YYYY)
    value           REAL,
    synced_at       TEXT,
    PRIMARY KEY (series_code, ref_date)
);
CREATE INDEX idx_obs_code ON series_observations(series_code);
CREATE INDEX idx_obs_date ON series_observations(ref_date);

-- Catalog: metadata for the 12 curated series (populated by ensure_schema).
CREATE TABLE series_catalog (
    code            INTEGER PRIMARY KEY,
    name            TEXT,
    frequency       TEXT,
    unit            TEXT,
    category        TEXT,
    description     TEXT
);

-- [v3] sync_state uses the v1 schema (series_code / last_date / synced_at /
-- row_count) instead of v2's generic (key / value / synced_at). The DROP
-- TABLE IF EXISTS before CREATE migrates old v1/v2 DBs automatically.
DROP TABLE IF EXISTS sync_state;
CREATE TABLE sync_state (
    series_code     TEXT PRIMARY KEY,     -- e.g. "11" or "11:2024-01-01:2024-12-31"
    last_date       TEXT,                 -- most recent ref_date synced
    synced_at       TEXT,                 -- ISO timestamp of the sync
    row_count       INTEGER               -- number of rows synced
);
```

---

## Data Flow

```text
BCB API (api.bcb.gov.br)
  ↓ httpx.get (Semaphore(5), 5-min cache)
fetcher.py → fetch_series() → [{ref_date, value}, ...]
  ↓ INSERT OR REPLACE
sync_engine.py → sgs.db (series_observations + sync_state)
  ↓ SELECT (read-only URI)
query_engine.py → {status, code, observations: [...]}
  ↓
skills/bcb/macro/modes/*.py → KPIs + chart sections + table sections
```

---

## Design Decisions

1. **Public API, no auth** — BCB SGS is free and requires no token. The fetcher uses a plain `httpx.get` with no headers.
2. **Thread-safe fetcher** — `Semaphore(5)` caps concurrent HTTP requests; `_cache_lock` guards the in-memory cache dict. Mirrors the brapi v1.1 pattern.
3. **Strict date normalization** — BCB returns dates as `DD/MM/YYYY`. The fetcher normalizes to `YYYY-MM-DD` at the ingest boundary so nothing downstream ever sees a `DD/MM/YYYY` string.
4. **String-to-float parsing** — BCB returns `valor` as a string with Portuguese comma decimals (`"10,234567"`). The fetcher replaces comma with dot and `float()`-parses.
5. **Idempotent sync** — `INSERT OR REPLACE` on `(series_code, ref_date)` primary key. Re-syncing replaces existing rows rather than appending duplicates.
6. **v1 sync_state schema with DROP TABLE migration** — `sync_state (series_code, last_date, synced_at, row_count)` gives structured per-series metadata. The `DROP TABLE IF EXISTS sync_state` in `ensure_schema` (before `CREATE`) ensures old v1/v2 DBs (which may have a different sync_state shape) get migrated cleanly. `CREATE TABLE IF NOT EXISTS` alone would not update an existing table's columns.
7. **12 curated series (v3)** — Covers the 4 macro categories. Includes TR (226) which was dropped in v2.

---

## Modes Summary

| Mode | Function | include_in_all | Description |
|------|----------|----------------|-------------|
| `sync_all` | `sync_engine.sync_all` | Yes | Sync all 12 series concurrently. |
| `sync_series` | `sync_engine.sync_series` | Yes | Sync one series (full history). |
| `sync_series_range` | `sync_engine.sync_series_range` | No | Sync a date window. |
| `series` | `query_engine.series` | Yes | Query N most-recent obs or window. |
| `last` | `query_engine.last_value` | Yes | Latest observation. |
| `search` | `query_engine.search` | No | LIKE search over catalog. |
| `summary` | `query_engine.summary` | Yes | Catalog overview sorted by (category, code). |
| `status` | `status_reporter.status` | Yes | DB stats: per-series row counts + sync timestamps. |

---

*Last updated: 2026-07-24 (v3.0).*
