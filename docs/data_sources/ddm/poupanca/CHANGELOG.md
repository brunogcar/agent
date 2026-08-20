# DDM Poupanca — Changelog

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `ddm/juros/`, adapted for
the SUM-derived poupanca historical series.

### Added (6 files)

- `data_sources/ddm/poupanca/__init__.py` — MANIFEST (8 modes) + `route()`
  dispatcher with lazy-import + kwargs filtering.
- `data_sources/ddm/poupanca/catalog.py` — `POUPANCA_CATALOG` (1 index:
  Poupanca), `SCHEMA_SQL` (with `acumulado_no_ano` + `acumulado_12m`
  columns using SUM, NOT `media_no_ano` + `media_12m` from juros which
  use AVERAGE), `ddm_data_dir()` / `db_path()` / `connect(read_only)` /
  `ensure_schema(conn)` / `index_url(slug)`.
- `data_sources/ddm/poupanca/fetcher.py` — `fetch_poupanca_page(slug, force)`
  with thread-safe 5-min cache + `Semaphore(5)`, `parse_matrix_only(html)`
  regex parser (12-month matrix only, NO "Ano" column, defensively
  filters stray "Ano" headers), `flatten_matrix_to_observations(matrix)`
  DERIVE pipeline computing `month_value` + `acumulado_no_ano` +
  `acumulado_12m` from the matrix using **SUM** (NOT AVERAGE like juros),
  `_parse_br_number` / `_parse_data_value` boundary normalizers.
- `data_sources/ddm/poupanca/sync_engine.py` — `sync_index(slug, force)` +
  `sync_all(force)` with `ThreadPoolExecutor(max_workers=3)`. Calls
  `parse_matrix_only` + `flatten_matrix_to_observations` before DB write.
- `data_sources/ddm/poupanca/query_engine.py` — `poupanca_history`,
  `last_value`, `monthly_matrix`, `search`, `summary`.
- `data_sources/ddm/poupanca/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE poupanca_observations (
    slug TEXT, ref_date TEXT,
    month_value REAL, acumulado_no_ano REAL, acumulado_12m REAL,
    synced_at TEXT,
    PRIMARY KEY (slug, ref_date)
);
```

### Boundary normalizations

| Raw DDM form                         | Normalized form | Field        |
| ------------------------------------ | --------------- | ------------ |
| matrix cell label `Jul` (column)     | `2026-07`       | `ref_date`   |
| `0,67`                               | `0.67`          | numeric      |
| `--`                                 | `None`          | numeric      |
| `<td data-value="0.67">0,67%</td>`   | `0.67`          | matrix cell  |

### Derive pipeline (new vs juros — KEY DIFFERENCE: SUM vs AVERAGE)

Because poupanca pages have NO historical table, the historical series is
derived from the matrix at parse time using **SUM** (NOT AVERAGE):

- `month_value`        = cell value (monthly yield % for that month)
- `acumulado_no_ano`   = SUM of all months in same year UP TO that month
                        (year-to-date cumulative return). Matches the Google
                        Sheet formula: `SUM(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`
- `acumulado_12m`      = SUM of last 12 months INCLUDING current (rolling
                        12-month cumulative return). Matches the Google Sheet
                        formula: `SUM(FILTER(B:B, A:A<=d, A:A>=d-365))`

For the first 11 months of the catalog (no full 12-month window),
`acumulado_12m` uses the available months (NOT None).

### Why SUM not AVERAGE?

Poupanca monthly yield is a **percentage return** (e.g. 0,67% means a 0.67%
return that month). Summing monthly returns produces the cumulative return
over the period (e.g. 12 months × ~0.6%/month ≈ 7.2%/year).

Juros uses AVERAGE because the monthly cell is a daily rate quoted as
**annualized %** - averaging produces the period-average annualized rate.

This matches the analyst's Google Sheet layout (SUM formulas for poupanca,
AVERAGE formulas for juros).

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-poupanca` entry:

```python
"ddm-poupanca": ("data_sources.ddm.poupanca.sync_engine", "sync_all",
                 lambda: {"force": True}),
```

`skills/ddm/poupanca/__init__.py` declares `REQUIRED_SOURCES = ["ddm"]` so
the sync guard auto-refreshes `ddm` (inflation) before each dashboard
run; the `ddm-poupanca` sync_map entry is available for explicit invocation
via `_trigger_sync("ddm-poupanca")` (e.g. from tests or manual sync flows).

### Tests

- `tests/data_sources/ddm/poupanca/test_fetcher.py` — 12 tests covering
  `_parse_br_number`, `_parse_data_value`, `parse_matrix_only` (years,
  month header with NO "Ano", data values, empty HTML, stray "Ano"
  filter), and `flatten_matrix_to_observations` (sorting, missing-cell
  skip, month_value, acumulado_no_ano SUM, acumulado_12m SUM full +
  short window + year-boundary cross, plus an explicit SUM-not-AVERAGE
  regression test).
- `tests/skills/ddm/poupanca/test_dashboard.py` — 11 tests covering tab
  structure (1 tab only), subtabs structure (Historico + Matriz), KPI
  promotion, 3-dataset chart, 4-column table with negative_red=True,
  NO "Ano" column in matrix, type="heatmap" section, {text, bg, color}
  cell dicts, Chart.js config emission, PT-BR formatting, section titles
  not repeating the index name.
