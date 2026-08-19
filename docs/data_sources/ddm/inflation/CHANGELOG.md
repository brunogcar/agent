# DDM Inflation — Changelog

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `bcb/sgs` + `bcb/focus`.

### Added (6 files)

- `data_sources/ddm/inflation/__init__.py` — MANIFEST (8 modes) + `route()`
  dispatcher with lazy-import + kwargs filtering.
- `data_sources/ddm/inflation/catalog.py` — `INDEX_CATALOG` (3 indices:
  IGP-M, IPCA, INPC), `SCHEMA_SQL`, `ddm_data_dir()` / `db_path()` /
  `connect(read_only)` / `ensure_schema(conn)` / `index_url(slug)`.
- `data_sources/ddm/inflation/fetcher.py` — `fetch_index_page(slug, force)`
  with thread-safe 5-min cache + `Semaphore(5)`, `parse_historical_table(html)`
  + `parse_monthly_matrix(html)` regex parsers, `_parse_mes_ano` /
  `_parse_br_number` / `_parse_data_value` boundary normalizers.
- `data_sources/ddm/inflation/sync_engine.py` — `sync_index(slug, force)` +
  `sync_all(force)` with `ThreadPoolExecutor(max_workers=3)`.
- `data_sources/ddm/inflation/query_engine.py` — `index_history`,
  `last_value`, `monthly_matrix`, `search`, `summary`.
- `data_sources/ddm/inflation/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE index_observations (
    slug TEXT, ref_date TEXT,
    month_value REAL, year_acumulado REAL, acumulado_12m REAL,
    synced_at TEXT,
    PRIMARY KEY (slug, ref_date)
);
```

### Boundary normalizations

| Raw DDM form                         | Normalized form | Field        |
| ------------------------------------ | --------------- | ------------ |
| `Jul/2026`                           | `2026-07`       | `ref_date`   |
| `0,41`                               | `0.41`          | numeric      |
| `--`                                 | `None`          | numeric      |
| `<td data-value="0.41">0,41%</td>`   | `0.41`          | matrix cell  |

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm` entry:

```python
"ddm": ("data_sources.ddm.inflation.sync_engine", "sync_all",
        lambda: {"force": True}),
```

`skills/ddm/inflation/__init__.py` declares `REQUIRED_SOURCES = ["ddm"]`
so the sync guard auto-refreshes `inflation.db` before each dashboard run.
