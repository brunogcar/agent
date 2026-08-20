# DDM Juros — Changelog

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `ddm/inflation/`, adapted
for the matrix-only juros pages (no historical table, no "Ano" column).

### Added (6 files)

- `data_sources/ddm/juros/__init__.py` — MANIFEST (8 modes) + `route()`
  dispatcher with lazy-import + kwargs filtering.
- `data_sources/ddm/juros/catalog.py` — `JUROS_CATALOG` (3 indices:
  Selic, Meta Selic, CDI), `SCHEMA_SQL` (with `media_no_ano` +
  `media_12m` columns instead of `year_acumulado` + `acumulado_12m`),
  `ddm_data_dir()` / `db_path()` / `connect(read_only)` /
  `ensure_schema(conn)` / `index_url(slug)`.
- `data_sources/ddm/juros/fetcher.py` — `fetch_juros_page(slug, force)`
  with thread-safe 5-min cache + `Semaphore(5)`, `parse_matrix_only(html)`
  regex parser (12-month matrix only, NO "Ano" column, defensively
  filters stray "Ano" headers), `flatten_matrix_to_observations(matrix)`
  DERIVE pipeline computing `month_value` + `media_no_ano` + `media_12m`
  from the matrix, `_parse_br_number` / `_parse_data_value` boundary
  normalizers.
- `data_sources/ddm/juros/sync_engine.py` — `sync_index(slug, force)` +
  `sync_all(force)` with `ThreadPoolExecutor(max_workers=3)`. Calls
  `parse_matrix_only` + `flatten_matrix_to_observations` before DB write.
- `data_sources/ddm/juros/query_engine.py` — `juros_history`, `last_value`,
  `monthly_matrix`, `search`, `summary`.
- `data_sources/ddm/juros/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE juros_observations (
    slug TEXT, ref_date TEXT,
    month_value REAL, media_no_ano REAL, media_12m REAL,
    synced_at TEXT,
    PRIMARY KEY (slug, ref_date)
);
```

### Boundary normalizations

| Raw DDM form                         | Normalized form | Field        |
| ------------------------------------ | --------------- | ------------ |
| matrix cell label `Jul` (column)     | `2026-07`       | `ref_date`   |
| `13,15`                              | `13.15`         | numeric      |
| `--`                                 | `None`          | numeric      |
| `<td data-value="13.15">13,15%</td>` | `13.15`         | matrix cell  |

### Derive pipeline (new vs inflation)

Because juros pages have NO historical table, the historical series is
derived from the matrix at parse time:

- `month_value`   = cell value (daily rate % for that month)
- `media_no_ano`  = AVG of all months in same year UP TO that month
                   (year-to-date average). Matches the Google Sheet formula:
                   `AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`
- `media_12m`     = AVG of last 12 months INCLUDING current (rolling 12m).
                   Matches the Google Sheet formula:
                   `AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))`

For the first 11 months of the catalog (no full 12-month window),
`media_12m` uses the available months (NOT None).

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-juros` entry:

```python
"ddm-juros": ("data_sources.ddm.juros.sync_engine", "sync_all",
              lambda: {"force": True}),
```

`skills/ddm/juros/__init__.py` declares `REQUIRED_SOURCES = ["ddm"]` so
the sync guard auto-refreshes `ddm` (inflation) before each dashboard
run; the `ddm-juros` sync_map entry is available for explicit invocation
via `_trigger_sync("ddm-juros")` (e.g. from tests or manual sync flows).
