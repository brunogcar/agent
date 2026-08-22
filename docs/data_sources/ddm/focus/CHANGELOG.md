# DDM Focus — Changelog

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `ddm/acoes/` (single-page
fetch), adapted for the Boletim Focus page (4 yearly tables × 12
indicators, CloudFront-protected, PT-BR value strings preserved verbatim).

### Added (6 files)

- `data_sources/ddm/focus/__init__.py` — MANIFEST (8 modes:
  `sync_all`, `sync_index`, `focus_data`, `last`, `search`, `summary`,
  `status`, `indicator`) + `route()` dispatcher with lazy-import +
  kwargs filtering. Both `focus_data` and `last` modes resolve to the
  same underlying `all_data()` query — `focus_data` is the user-facing
  alias for `last`.
- `data_sources/ddm/focus/catalog.py` — `FOCUS_URL =
  "https://www.dadosdemercado.com.br/boletim-focus"`, `SCHEMA_SQL`
  (`focus_observations` table with `(year, indicator, ref_date)` PK,
  `four_weeks_ago` / `one_week_ago` / `today` TEXT columns preserving
  the PT-BR source strings, `comparison` TEXT column ("up"/"down"/
  "flat"/""), `respondents` INTEGER, `ref_date` YYYY-MM-DD, `synced_at`
  ISO timestamp; `sync_state` table for sync metadata),
  `ddm_data_dir()` / `db_path()` / `connect(read_only)` /
  `ensure_schema(conn)` / `focus_url()`.
- `data_sources/ddm/focus/fetcher.py` — `fetch_focus_page(force)` with
  thread-safe 5-min cache + `Semaphore(5)`. Sends the **full Chrome 127
  browser header set** (User-Agent + Accept + Accept-Language +
  Accept-Encoding + Connection + Upgrade-Insecure-Requests) because
  the `/boletim-focus` endpoint is CloudFront-protected and rejects
  bare User-Agents with a 403. `parse_focus_tables(html)` regex parser
  handling 4 yearly tables: per-table year identification from the
  nearest preceding `<h2>`/`<h3>` heading containing a 4-digit year
  (no hardcoded "table N is year X" mapping — robust to page reorders).
  `_parse_int` (handles "149" and "149 resp." residue),
  `_normalize_comparison` (maps `▲`/`▼`/`=` glyphs + "Alta"/"Baixa"/
  "Estavel" word fallbacks to `"up"`/`"down"`/`"flat"`), `_strip_html`.
- `data_sources/ddm/focus/sync_engine.py` — `sync_all(force)` +
  `sync_index(slug="focus", force)` (alias). Single HTTP call (no
  ThreadPoolExecutor — the focus page is one document). Calls
  `parse_focus_tables` before DB write. INSERT OR REPLACE on
  `(year, indicator, ref_date)` PK for idempotency. Different ref_dates
  accumulate into a history series (Focus is weekly).
- `data_sources/ddm/focus/query_engine.py` — `focus_by_year(year)`,
  `focus_by_indicator(indicator)`, `last_value()`, `search(query,
  limit)`, `summary()`, `all_data()`. All queries filter to the latest
  `ref_date` by default so callers see the current Focus bulletin.
  Historical ref_dates are preserved in the DB for future time-series
  features.
- `data_sources/ddm/focus/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE focus_observations (
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
CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
```

### Boundary normalizations

| Raw DDM form                  | Normalized form      | Field             |
| ----------------------------- | -------------------- | ----------------- |
| `5,151%`                      | `"5,151%"`           | value columns     |
| `R$ 5,200`                    | `"R$ 5,200"`         | value columns     |
| `149`                         | `149`                | `respondents`     |
| `149 resp.`                   | `149`                | `respondents`     |
| `▲` (U+25B2)                  | `"up"`               | `comparison`      |
| `▼` (U+25BC)                  | `"down"`             | `comparison`      |
| `=` (U+003D)                  | `"flat"`             | `comparison`      |
| `Alta` / `Baixa` / `Estavel`  | `"up"` / `"down"` / `"flat"` | `comparison` |
| `<a href="...">IPCA</a>`      | `IPCA`               | `indicator`       |
| `--`                          | `None`               | any numeric       |

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-focus` entry:

```python
"ddm-focus": ("data_sources.ddm.focus.sync_engine", "sync_all",
              lambda: {"force": True}),
```

`skills/ddm/focus/__init__.py` declares `REQUIRED_SOURCES = ["ddm-focus"]`
so the sync guard auto-refreshes `focus.db` before each dashboard run.

`skills/_freshness.py` also gained a `ddm-focus` entry in
`get_freshness()` so consumers can poll the last-sync timestamp for any
DDM sub-domain from a single dict (now 5 keys: `ddm`, `ddm-juros`,
`ddm-poupanca`, `ddm-acoes`, `ddm-focus`).

### Tests

- `tests/data_sources/ddm/focus/test_fetcher.py` — 18 tests covering
  `_parse_int` (basic, suffix-strip, missing values),
  `_normalize_comparison` (up/down/flat glyphs, word fallbacks, empty),
  `_strip_html` (anchor + tag stripping),
  `_find_year_for_table` (h2/h3/nearest/none),
  `parse_focus_tables` (rows per table, year extraction, value-string
  preservation, currency preservation, comparison normalization, empty
  HTML, malformed-row skip, header-repeat skip, h3 year heading).
- `tests/skills/ddm/focus/test_dashboard.py` — 24 tests covering tab
  structure (13 tabs: 1 Focus + 12 indicators), tab groups (Boletim /
  Indicadores), Focus tab 4 year subtabs, indicator tab 3 time-window
  subtabs + chart, KPI promotion (4 top-level KPIs), year table
  sortable features (`sortable=True` + `default_sort` + `sort_types` +
  `column_align` + 12 indicator rows + numeric-cell dict shape +
  comparison cell color + respondents data-value), indicator table
  sortable features (4 year rows + sort_types with number for Ano),
  chart structure (3 datasets + dataset labels + dataset colors +
  X-axis labels + data-points match years + bar type).
