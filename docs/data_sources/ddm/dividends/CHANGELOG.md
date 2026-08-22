# DDM Dividends — Changelog

## v1.0 — 2026-07

Initial release. Subdomain pattern mirroring `ddm/inflation/juros/poupanca`,
adapted for the single-page dividend agenda (1 table, ~200 rows, 2 tipos).

### Added (6 files)

- `data_sources/ddm/dividends/__init__.py` — MANIFEST (8 modes) + `route()`
  dispatcher with lazy-import + kwargs filtering.
- `data_sources/ddm/dividends/catalog.py` — `DIVIDENDS_URL` constant,
  `TIPOS` tuple, `SORT_KEYS` whitelist, `SCHEMA_SQL` (2 tables:
  `dividends` + `sync_state`), `ddm_data_dir()` / `db_path()` /
  `connect(read_only)` / `ensure_schema(conn)`.
- `data_sources/ddm/dividends/fetcher.py` — `fetch_dividends_page(force)`
  with thread-safe 5-min cache + `Semaphore(5)`, `parse_dividends_table(html)`
  regex parser (finds `<table class="normal-table">`, extracts ticker from
  `<a>` tag with fallback to stripped HTML), `_parse_br_number` /
  `_parse_br_date` / `_extract_ticker` boundary normalizers.
- `data_sources/ddm/dividends/sync_engine.py` — `sync_all(force)` +
  `sync_index(slug, force)` alias. Single HTTP call + parse + DB write.
- `data_sources/ddm/dividends/query_engine.py` — `dividends_list`,
  `last_value`, `search`, `ticker_history`, `summary`. `order_by` +
  `direction` validated against `SORT_KEYS` whitelist (safe string
  interpolation into SQL).
- `data_sources/ddm/dividends/status_reporter.py` — `status()` returns
  DB stats + by-tipo counts + last sync timestamp.

### Schema

```sql
CREATE TABLE dividends (
    ticker TEXT, tipo TEXT, value REAL,
    record_date TEXT, ex_date TEXT, payment_date TEXT,
    synced_at TEXT,
    PRIMARY KEY (ticker, record_date, tipo)
);
```

### Boundary normalizations

| Raw DDM form                                | Normalized form   | Field         |
| ------------------------------------------- | ----------------- | ------------- |
| `<a href="/acoes/bbdc3">BBDC3</a>`          | `"BBDC3"`         | ticker        |
| `Dividendo` / `JCP`                         | `"Dividendo"` / `"JCP"` | tipo    |
| `0,017250`                                  | `0.017250`        | value (REAL)  |
| `01/07/2026` (DD/MM/YYYY)                   | `"2026-07-01"`    | record_date / ex_date / payment_date (TEXT) |

DB stores dates as ISO `YYYY-MM-DD`; the dashboard converts to PT-BR
`DD/MM/YYYY` for display.

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-dividends` entry:

```python
"ddm-dividends": ("data_sources.ddm.dividends.sync_engine", "sync_all",
                  lambda: {"force": True}),
```

`skills/ddm/dividends/__init__.py` declares
`REQUIRED_SOURCES = ["ddm-dividends"]` so the sync guard auto-refreshes
the dividends DB before each dashboard run.

### Freshness tracking

`skills/_freshness.py` (and the mirrored `skills/cvm/_freshness.py` for
the cvm-subfolder layout) gained a `ddm-dividends` entry that reads
`synced_at` from the dividends DB's `sync_state` table:

```python
try:
    from data_sources.ddm.dividends.catalog import db_path as ddm_div_path
    result["ddm-dividends"] = _check_db_freshness(ddm_div_path())
except Exception:
    result["ddm-dividends"] = ""
```

### Tests

- `tests/data_sources/ddm/dividends/test_fetcher.py` — 12 tests covering
  `_parse_br_number`, `_parse_br_date`, `_extract_ticker` (anchor +
  fallback), `parse_dividends_table` (row count, row shape, first row
  values, JCP row, value range extremes, no-anchor fallback, empty HTML,
  no-table, short-row skip, table-by-class preference).
- `tests/skills/ddm/dividends/test_dashboard.py` — 18 tests covering
  tab structure (1 tab), KPI labels + values, distribution chart
  (grouped bar, 8 buckets, bucket counts, colors), sortable table
  (6 columns, column_align, sort_types, default_sort, no negative_red,
  dates as PT-BR, numeric cell as dict with data_value, small vs large
  value formatting, ticker+tipo as plain strings), error-path graceful
  degradation.
