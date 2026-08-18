<- Back to [FOCUS](../FOCUS.md)

# 🤖 FOCUS -- AI Editing Instructions

Rules for AI agents editing the BCB Focus data source. Follow these to avoid breaking the contracts that tests + downstream skills rely on.

## NEVER DO

1. **NEVER remove any of the 4 indicators** from `INDICATOR_CATALOG` (IPCA, Selic, PIB, Cambio). The `expectations` mode renders one panel per indicator; removing one breaks the dashboard layout.
2. **NEVER change the composite PK** of `expectations_monthly` away from `(indicador, data, data_referencia, base_calculo)`. The `base_calculo` field distinguishes current-month (0) vs forward-month (1) expectations for the same (indicador, data, data_referencia). Without it, syncs would silently overwrite.
3. **NEVER change the composite PK** of `expectations_annual` away from `(indicador, data, data_referencia)`. Annual expectations don't use `base_calculo` (the field is NULL for annual), so it's not in the PK.
4. **NEVER use `date` as the field name** in query_engine return payloads -- use `data` consistently (Olinda's field name). The expectations mode reads `o["data"]`.
5. **NEVER store raw `T00:00:00` datetime strings** in the DB. The fetcher truncates to `YYYY-MM-DD` at the ingest boundary -- keep it that way.
6. **NEVER use em-dashes (--) or en-dashes (-)** in Python strings. Use ASCII hyphens (-). The test suite runs with `-W error` which turns `DeprecationWarning` into errors.
7. **NEVER add `__init__.py` to test directories.** Tests use `--import-mode=importlib` semantics.
8. **NEVER mock the DB in test fixtures** -- create a REAL temp SQLite DB with real test data.
9. **NEVER use double quotes in OData `$filter` values** -- OData requires single quotes (`$filter=Indicador eq 'IPCA'`). Double quotes return an empty result set.
10. **NEVER assume `Media`/`Mediana`/`Minimo`/`Maximo` are non-null** -- some Olinda rows have NULL fields (rare but happens for indicators with few respondents). The fetcher's `_parse_value` returns None for these.

## ALWAYS DO

1. **ALWAYS add new indicators to `INDICATOR_CATALOG`** in `catalog.py` (not just the DB). The catalog is the source of truth.
2. **ALWAYS use `INSERT OR REPLACE`** for sync operations -- the composite PK enforces idempotency.
3. **ALWAYS call `ensure_schema(conn)`** before writing -- it creates tables + indexes.
4. **ALWAYS normalize dates in the fetcher** (`_normalize_date`), not in the query engine or sync engine.
5. **ALWAYS use `read_only=True`** for query_engine connections (SQLite URI `?mode=ro` fails fast if DB missing).
6. **ALWAYS filter kwargs by signature** in the route() dispatcher (`inspect.signature(fn)`).
7. **ALWAYS return a structured dict** with `status` field (`ok` / `error` / `not_found` / `not_synced` / `partial`) from every mode function.
8. **ALWAYS keep the fetcher thread-safe** -- guard `_cache` with `_cache_lock`, cap concurrency with `Semaphore(5)`.
9. **ALWAYS use single quotes in OData `$filter`** values: `$filter=Indicador eq 'IPCA'`.
10. **ALWAYS pass `$orderby=Data desc` + `$top=N`** when fetching -- otherwise Olinda returns the oldest N records (not the most recent).

## Test Directory Layout

```text
tests/
└── data_sources/bcb/focus/
    ├── conftest.py        # focus_db fixture (real temp DB)
    ├── test_catalog.py    # INDICATOR_CATALOG + schema tests
    ├── test_query.py      # query_engine tests (uses focus_db)
    └── test_sync.py       # sync_engine tests (mocks the fetcher)
```

**NO `__init__.py` anywhere in `tests/`.**

---

*Last updated: 2026-08-22 (v1.0).*
