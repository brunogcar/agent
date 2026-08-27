# DDM Fluxo — Changelog

## v1.1 — 2026-08-27

**Incremental sync — only INSERT new rows (no gaps).**

### I12: Incremental sync

- `sync_all(force=False)` now queries `MAX(ref_date)` from the DB and only
  INSERTs rows with `ref_date > latest_in_db`. This avoids re-inserting
  ~750 existing rows on every sync.
- When `force=True`, falls back to full-refresh (DELETE + re-INSERT all rows)
  to handle corrections (DDM may revise historical data).
- If no new rows exist, skips the DB write entirely (returns `skipped=True`).
- **No gaps**: the fetcher still fetches the full page (~750 rows), but only
  new rows are written. If you sync after a gap (e.g., didn't sync for a week),
  all missing days are inserted in one pass.

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `ddm/focus/` (single-page
fetch), adapted for the /fluxo page (1 table × ~247 daily rows × 6
columns of investor flow, CloudFront-protected, PT-BR values parsed to
REAL at the fetcher boundary).

### Added (6 files)

- `data_sources/ddm/fluxo/__init__.py` — MANIFEST (8 modes:
  `sync_all`, `sync_index`, `fluxo_data`, `last`, `search`, `summary`,
  `status`, `ticker`) + `route()` dispatcher with lazy-import +
  kwargs filtering.
- `data_sources/ddm/fluxo/catalog.py` — `FLUXO_URL =
  "https://www.dadosdemercado.com.br/fluxo"`, `SCHEMA_SQL`
  (`fluxo_observations` table with `ref_date` PK, 5 REAL investor
  columns (`estrangeiro` / `institucional` / `pessoa_fisica` /
  `inst_financeira` / `outros`), `synced_at` ISO timestamp;
  `sync_state` table for sync metadata), `ddm_data_dir()` /
  `db_path()` / `connect(read_only)` / `ensure_schema(conn)` /
  `fluxo_url()`.
- `data_sources/ddm/fluxo/fetcher.py` — `fetch_fluxo_page(force)` with
  thread-safe 5-min cache + `Semaphore(5)`. Sends the **full Chrome 127
  browser header set** (User-Agent + Accept + Accept-Language +
  Connection + Upgrade-Insecure-Requests) because the `/fluxo` endpoint
  is CloudFront-protected and rejects bare User-Agents with a 403.
  `parse_fluxo_table(html)` regex parser handling the single
  `<table class="normal-table" id="flow">` (6 columns × ~247 rows).
  `_parse_br_number` (strips "mi" suffix, removes dot thousands,
  replaces comma decimal, preserves sign), `_parse_br_date` (DD/MM/YYYY
  → YYYY-MM-DD), `_strip_html`.
- `data_sources/ddm/fluxo/sync_engine.py` — `sync_all(force)` +
  `sync_index(slug="fluxo", force)` (alias). Single HTTP call (no
  ThreadPoolExecutor — the fluxo page is one document). Calls
  `parse_fluxo_table` before DB write. INSERT OR REPLACE on `ref_date`
  PK for idempotency. `last_date` = max(ref_date in observations).
- `data_sources/ddm/fluxo/query_engine.py` — `fluxo_data(limit)`,
  `fluxo_by_investor(investor, limit)`, `last_value()`, `by_date(date)`,
  `search(query, limit)`, `summary()`, `monthly_cumulative(investor)`,
  `annual_cumulative(investor)`. The `monthly_cumulative` query groups
  by `SUBSTR(ref_date, 1, 7)` (YYYY-MM) and SUMs the daily values; the
  `annual_cumulative` query produces a running cumulative sum (each
  day = previous + today) by iterating rows in ASC order in Python.
- `data_sources/ddm/fluxo/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE fluxo_observations (
    ref_date        TEXT NOT NULL,
    estrangeiro     REAL,
    institucional   REAL,
    pessoa_fisica   REAL,
    inst_financeira REAL,
    outros          REAL,
    synced_at       TEXT,
    PRIMARY KEY (ref_date)
);
CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
```

### Boundary normalizations

| Raw DDM form          | Normalized form   | Field                       |
| --------------------- | ----------------- | --------------------------- |
| `19/08/2026`          | `"2026-08-19"`    | `ref_date`                  |
| `-1.582,35 mi`        | `-1582.35`        | value columns               |
| `1.029,81 mi`         | `1029.81`         | same                        |
| `42,36 mi`            | `42.36`           | same                        |
| `-9,31 mi`            | `-9.31`           | same                        |
| `1.234.567,89 mi`     | `1234567.89`      | same                        |
| `0,00 mi`             | `0.0`             | same                        |
| `--`                  | `None`            | any numeric                 |

### Sync wiring

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm-fluxo` entry:

```python
"ddm-fluxo": ("data_sources.ddm.fluxo.sync_engine", "sync_all",
              lambda: {"force": True}),
```

`skills/ddm/fluxo/__init__.py` declares `REQUIRED_SOURCES = ["ddm-fluxo"]`
so the sync guard auto-refreshes `fluxo.db` before each dashboard run.

`skills/_freshness.py` also gained a `ddm-fluxo` entry in
`get_freshness()` so consumers can poll the last-sync timestamp for any
DDM sub-domain from a single dict (now 6 keys: `ddm`, `ddm-juros`,
`ddm-poupanca`, `ddm-acoes`, `ddm-focus`, `ddm-fluxo`).

### Tests

- `tests/data_sources/ddm/fluxo/test_fetcher.py` — 17 tests covering
  `_parse_br_number` (negative + thousands, positive + thousands, no
  thousands, negative no thousands, large value, zero, missing values,
  case-insensitive "mi"), `_parse_br_date` (PT-BR to ISO, single-digit
  day/month, invalid input), `_strip_html`, `parse_fluxo_table` (3 rows,
  ref_date ISO, value parsing to floats, negative in all columns, empty
  HTML, malformed-row skip, header-row skip, no-class fallback,
  source-order preservation).
- `tests/skills/ddm/fluxo/test_dashboard.py` — 30 tests covering tab
  structure (5 tabs: 1 Fluxo + 4 investors), tab groups (Fluxo /
  Investidores), Fluxo tab chart + table, investor tab 3 subtabs
  (Diario / Mensal / Anual), each subtab's chart + table, KPI promotion
  (5 top-level KPIs: 1 date + 4 investor totals), Fluxo table sortable
  features (`sortable=True` + `default_sort` DESC + `sort_types` +
  `column_align` + `negative_red=True` + 6 columns + numeric-cell
  `data-value` + date-cell DD/MM/YYYY display), investor table sortable
  features (2 columns + `negative_red=True`), chart structure
  (4 datasets in Fluxo chart + dataset labels + dataset colors + bar
  type + range selector, 1 dataset in daily chart + per-bar green/red
  colors + range selector, line chart in monthly + annual, range
  selector in annual).
