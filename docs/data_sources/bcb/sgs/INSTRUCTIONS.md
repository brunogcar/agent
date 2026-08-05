<- Back to [SGS](../SGS.md)

# 🤖 SGS — AI Editing Instructions

Rules for AI agents editing the BCB SGS data source. Follow these to avoid breaking the contracts that tests + downstream skills rely on.

## NEVER DO

1. **NEVER remove series 226 (TR) from SERIES_CATALOG** — it was dropped in v2 and restored in v3. Removing it breaks `test_catalog_has_series_226_tr` + the rates mode KPI.
2. **NEVER change the sync_state schema** away from `(series_code, last_date, synced_at, row_count)`. The DROP TABLE migration in `ensure_schema` depends on this shape. v2 used `(key, value, synced_at)` — do not go back.
3. **NEVER remove the `DROP TABLE IF EXISTS sync_state`** line from SCHEMA_SQL. Without it, old v1/v2 DBs with a different sync_state shape won't migrate (CREATE TABLE IF NOT EXISTS doesn't update existing tables).
4. **NEVER use `date` as the field name** in query_engine return payloads — use `ref_date` consistently. The macro skill's helpers + report builders read `o["ref_date"]`.
5. **NEVER store raw `DD/MM/YYYY` dates** in the DB. The fetcher normalizes to `YYYY-MM-DD` at the ingest boundary — keep it that way.
6. **NEVER use em-dashes (—) or en-dashes (–)** in Python strings. Use ASCII hyphens (-). The test suite runs with `-W error` which turns `DeprecationWarning` into errors; some linters also flag non-ASCII in source.
7. **NEVER add `__init__.py` to test directories.** Tests use `--import-mode=importlib` semantics; `__init__.py` in test dirs causes package-name collisions with the real `data_sources`/`skills` packages.
8. **NEVER add a root-level `conftest.py`** (at `/home/z/bcb-sgs-v3/conftest.py`). Only `tests/data_sources/bcb/sgs/conftest.py` is allowed.
9. **NEVER mock the DB in the `sgs_db` fixture** — it must create a REAL temp SQLite DB with real test data (per CRITICAL RULE 9).

## ALWAYS DO

1. **ALWAYS add new series to SERIES_CATALOG** in `catalog.py` (not just the DB). The catalog is the source of truth — `ensure_schema` populates `series_catalog` from it.
2. **ALWAYS use `INSERT OR REPLACE`** for sync operations — the `(series_code, ref_date)` PK enforces idempotency.
3. **ALWAYS call `ensure_schema(conn)`** before writing — it creates tables + populates the catalog + migrates old DBs.
4. **ALWAYS normalize dates in the fetcher** (`_normalize_date`), not in the query engine or sync engine.
5. **ALWAYS use `read_only=True`** for query_engine connections (SQLite URI `?mode=ro` fails fast if DB missing).
6. **ALWAYS filter kwargs by signature** in the route() dispatcher (`inspect.signature(fn)`) — prevents `TypeError: unexpected keyword argument` from caller mistakes.
7. **ALWAYS return a structured dict** with `status` field (`ok` / `error` / `not_found` / `not_synced` / `partial`) from every mode function.
8. **ALWAYS keep the fetcher thread-safe** — guard `_cache` with `_cache_lock`, cap concurrency with `Semaphore(5)`.
9. **ALWAYS run tests with `pytest tests/data_sources/bcb/ tests/skills/bcb/ -v -W error`** before committing. The `-W error` flag catches deprecation warnings (e.g. non-ASCII in source).

## Test Directory Layout

```text
tests/
├── data_sources/bcb/sgs/
│   ├── conftest.py        # sgs_db fixture (real temp DB)
│   ├── test_catalog.py    # SERIES_CATALOG + schema tests
│   └── test_query.py      # query_engine tests (uses sgs_db)
└── skills/bcb/macro/
    └── test_modes.py      # macro skill modes (mocks query_engine)
```

**NO `__init__.py` anywhere in `tests/`.** The conftest.py is only in `tests/data_sources/bcb/sgs/` — there is no root-level conftest.py.

---

*Last updated: 2026-07-24 (v3.0).*
