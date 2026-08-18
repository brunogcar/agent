<- Back to [FOCUS](../FOCUS.md)

# 🏗️ FOCUS Architecture

## File Map

```text
data_sources/bcb/focus/
├── __init__.py            # MANIFEST + route() dispatcher (7 modes)
├── catalog.py             # INDICATOR_CATALOG (4 indicators) + SCHEMA_SQL + connect/ensure_schema
├── fetcher.py             # OData HTTP fetcher (thread-safe, Semaphore(5), 5-min cache)
├── sync_engine.py         # sync_expectations / sync_all / sync_indicator
├── query_engine.py        # expectations / last_value / summary
└── status_reporter.py     # status() -- DB stats
```

---

## Schema (3 tables)

```sql
-- Monthly expectations: one row per (indicador, data, data_referencia, base_calculo).
-- base_calculo: 0 = current month, 1 = next month onward (BCB convention).
CREATE TABLE expectations_monthly (
    indicador            TEXT NOT NULL,
    data                 TEXT NOT NULL,        -- YYYY-MM-DD (date expectation was made)
    data_referencia      TEXT NOT NULL,        -- 'MM/YYYY' for monthly
    media                REAL,
    mediana              REAL,
    minimo               REAL,
    maximo               REAL,
    numero_respondentes INTEGER,
    base_calculo         INTEGER,
    synced_at            TEXT,
    PRIMARY KEY (indicador, data, data_referencia, base_calculo)
);
CREATE INDEX idx_exp_monthly_ind  ON expectations_monthly(indicador);
CREATE INDEX idx_exp_monthly_ref  ON expectations_monthly(data_referencia);
CREATE INDEX idx_exp_monthly_date ON expectations_monthly(data);

-- Annual expectations: one row per (indicador, data, data_referencia).
-- No base_calculo in PK (annual expectations don't use it).
CREATE TABLE expectations_annual (
    indicador            TEXT NOT NULL,
    data                 TEXT NOT NULL,
    data_referencia      TEXT NOT NULL,        -- 'YYYY' for annual
    media                REAL,
    mediana              REAL,
    minimo               REAL,
    maximo               REAL,
    numero_respondentes INTEGER,
    base_calculo         INTEGER,
    synced_at            TEXT,
    PRIMARY KEY (indicador, data, data_referencia)
);
CREATE INDEX idx_exp_annual_ind  ON expectations_annual(indicador);
CREATE INDEX idx_exp_annual_ref  ON expectations_annual(data_referencia);
CREATE INDEX idx_exp_annual_date ON expectations_annual(data);

-- Sync state: one row per indicador (mirrors the sgs sync_state pattern).
CREATE TABLE sync_state (
    indicador   TEXT PRIMARY KEY,
    frequency   TEXT,
    last_date   TEXT,
    synced_at   TEXT,
    row_count   INTEGER
);
```

---

## Data Flow

```text
BCB Olinda OData API (olinda.bcb.gov.br)
  | httpx.get (Semaphore(5), 5-min cache)
fetcher.py -> fetch_expectations() -> [{data, data_referencia, media, mediana, ...}, ...]
  | INSERT OR REPLACE
sync_engine.py -> focus.db (expectations_monthly + expectations_annual + sync_state)
  | SELECT (read-only URI)
query_engine.py -> {status, indicador, frequency, observations: [...]}
  |
skills/bcb/macro/modes/expectations.py -> KPIs + chart sections + table sections
```

---

## Design Decisions

1. **Public API, no auth** -- BCB Olinda OData is free and requires no token. The fetcher uses a plain `httpx.get` with `Accept: application/json`.
2. **Thread-safe fetcher** -- `Semaphore(5)` caps concurrent HTTP requests; `_cache_lock` guards the in-memory cache dict. Mirrors the sgs fetcher pattern.
3. **Strict date normalization** -- Olinda returns dates as ISO `YYYY-MM-DD` (sometimes with a `T00:00:00` time component). The fetcher truncates to the date part so nothing downstream sees a datetime string.
4. **Defensive number parsing** -- Olinda returns numbers as JSON numbers (already float), but `_parse_value` + `_parse_int` handle nulls + string edge cases defensively.
5. **Idempotent sync** -- `INSERT OR REPLACE` on the composite primary key per table. Re-syncing replaces existing rows rather than appending duplicates.
6. **Two tables, not one** -- monthly + annual expectations have different `DataReferencia` formats (`MM/YYYY` vs `YYYY`) and different PK requirements (monthly has `base_calculo` in the PK; annual doesn't). Splitting avoids NULL-able PK columns.
7. **4 curated indicators** -- covers the 4 macro categories (Juros / Inflacao / Atividade / Cambio). Each indicator has a primary frequency in `DEFAULT_INDICATORS`.
8. **OData query convention** -- `$filter` values use single quotes (`'IPCA'`), `$orderby=Data desc` for most-recent-first, `$top=N` for limit, `$format=json` for JSON response.
9. **Cache key = (indicador, frequency, top)** -- the cache is per-indicator + per-frequency + per-top so different `top` values don't collide.
10. **Auto-discovery** -- `data_sources/bcb/__init__.py`'s `_discover_sub_domains()` scans for any sub-directory with `__init__.py` + `MANIFEST` + `route()`, so adding `focus/` is enough -- no edits to the parent `__init__.py` are needed.

---

## Modes Summary

| Mode | Function | include_in_all | Description |
|------|----------|----------------|-------------|
| `sync_all` | `sync_engine.sync_all` | Yes | Sync all 4 indicators concurrently. |
| `sync_expectations` | `sync_engine.sync_expectations` | Yes | Sync one (indicador, frequency) pair. |
| `sync_indicator` | `sync_engine.sync_indicator` | No | Sync one indicator (primary frequency). |
| `expectations` | `query_engine.expectations` | Yes | Query most-recent N expectations. |
| `last` | `query_engine.last_value` | Yes | Latest expectation. |
| `summary` | `query_engine.summary` | Yes | Catalog overview + row counts. |
| `status` | `status_reporter.status` | Yes | DB stats: per-indicator row counts + sync timestamps. |

---

*Last updated: 2026-08-22 (v1.0).*
