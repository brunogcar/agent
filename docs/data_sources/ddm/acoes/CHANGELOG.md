# DDM Acoes — Changelog

## v1.0 — 2025-01

Initial release. Subdomain pattern mirroring `ddm/inflation/` +
`ddm/juros/` + `ddm/poupanca/`, adapted for the flat stocks-list page
(single HTML table, no per-index historical series).

### Added (6 files)

- `data_sources/ddm/acoes/__init__.py` — MANIFEST (8 modes:
  `sync_all`, `sync_index`, `stocks`, `last`, `search`, `summary`,
  `status`, `ticker`) + `route()` dispatcher with lazy-import +
  kwargs filtering. Both `last` and `ticker` modes resolve to the same
  underlying `last_value(ticker)` query — `ticker` is the user-facing
  alias for `last`.
- `data_sources/ddm/acoes/catalog.py` — `ACOES_PATH = "/acoes"`,
  `SCHEMA_SQL` (`stocks` table with `ticker` PK, `name`, `negocios`,
  `last_price`, `variation`, `synced_at`, `ref_date`; `sync_state` table
  for sync metadata), `ddm_data_dir()` / `db_path()` /
  `connect(read_only)` / `ensure_schema(conn)` / `acoes_url()`.
- `data_sources/ddm/acoes/fetcher.py` — `fetch_acoes_page(force)` with
  thread-safe 5-min cache + `Semaphore(5)`, `parse_stocks_table(html)`
  regex parser (5-column table: Ticker | Nome | Negocios | Ultima (R$) |
  Variacao), `_parse_br_int` (PT-BR thousands "52.792.400" → 52792400),
  `_parse_br_number` (PT-BR decimal "44,30" → 44.30), `_parse_variation`
  (signed "+2,78%" → 2.78 / "-10,85%" → -10.85).
- `data_sources/ddm/acoes/sync_engine.py` — `sync_all(force)` +
  `sync_index(slug="acoes", force)` (alias). Single HTTP call (no
  ThreadPoolExecutor — the acoes page is one document). Calls
  `parse_stocks_table` before DB write. INSERT OR REPLACE on `ticker` PK
  for idempotency.
- `data_sources/ddm/acoes/query_engine.py` — `stocks_list(order_by,
  direction, limit)`, `stocks(...)` (alias), `last_value(ticker)`,
  `search(query, limit)`, `summary()`. Whitelist of sortable columns
  (`_SORT_COLUMNS`) defends against SQL injection.
- `data_sources/ddm/acoes/status_reporter.py` — `status()`.

### Schema

```sql
CREATE TABLE stocks (
    ticker        TEXT PRIMARY KEY,
    name          TEXT,
    negocios      INTEGER,
    last_price    REAL,
    variation     REAL,
    synced_at     TEXT,
    ref_date      TEXT
);
CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
```

### Boundary normalizations

| Raw DDM form                     | Normalized form | Field        |
| -------------------------------- | --------------- | ------------ |
| `52.792.400`                     | `52792400`      | `negocios`   |
| `44,30`                          | `44.30`         | `last_price` |
| `+2,78%`                         | `2.78`          | `variation`  |
| `-10,85%`                        | `-10.85`        | `variation`  |
| `<a href="/acoes/petr4">PETR4</a>` | `PETR4`       | `ticker`     |
| `--`                             | `None`          | any numeric  |

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-acoes` entry:

```python
"ddm-acoes": ("data_sources.ddm.acoes.sync_engine", "sync_all",
              lambda: {"force": True}),
```

`skills/ddm/acoes/__init__.py` declares `REQUIRED_SOURCES = ["ddm-acoes"]`
so the sync guard auto-refreshes `acoes.db` before each dashboard run
(the only DDM skill that uses its own source key — inflation uses `"ddm"`,
juros uses `"ddm-juros"`, poupanca uses `"ddm-poupanca"`).

`skills/_freshness.py` (NEW top-level freshness helper) also gained a
`ddm-acoes` entry in `get_freshness()` so consumers can poll the
last-sync timestamp for any DDM sub-domain from a single dict.

### Tests

- `tests/data_sources/ddm/acoes/test_fetcher.py` — 14 tests covering
  `_parse_br_int`, `_parse_br_number`, `_parse_variation` (with sign,
  without sign, missing values), `parse_stocks_table` (page order,
  fields, negative variation, anchor-tag stripping, empty HTML,
  `normal-table` fallback, malformed-row skip).
- `tests/skills/ddm/acoes/test_dashboard.py` — 16 tests covering tab
  structure (1 tab + group="Acoes"), KPI promotion (4 KPIs: Total de
  Acoes + Mais Negociada + Maior Alta + Maior Baixa), sortable table
  (`sortable=True` + `default_sort` + `sort_types` + `column_align` +
  `negative_red` + 5 columns + numeric-cell dict shape + variation
  text sign), and price-distribution chart (16 bars, counts match input
  prices, bar colors match `skills._price_colors.ALL_RANGES` palette,
  chart + section titles).
