# DDM Fluxo — Architecture

Sub-domain: **`fluxo`**
Domain: `ddm`
Mirrors: `data_sources/ddm/focus/` (file layout + sync pattern, adapted
        for the single-table fluxo page with daily investment flow data).

## File map (6 files)

```
data_sources/ddm/fluxo/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # FLUXO_URL, SCHEMA_SQL, ddm_data_dir(),
│                        #   db_path(), connect(read_only), ensure_schema,
│                        #   fluxo_url()
├── fetcher.py           # fetch_fluxo_page (full Chrome 127 browser
│                        #   headers for CloudFront), parse_fluxo_table,
│                        #   _parse_br_number, _parse_br_date, _strip_html
├── sync_engine.py       # sync_all(force), sync_index(slug, force)
├── query_engine.py      # fluxo_data, fluxo_by_investor, last_value,
│                        #   by_date, search, summary, monthly_cumulative,
│                        #   annual_cumulative
└── status_reporter.py   # status()
```

## Database

`memory_db/ddm/fluxo.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db` + `juros.db` +
`poupanca.db` + `acoes.db` + `focus.db` (`memory_db/ddm/`) - all 6 are
per-subdomain DBs under the ddm domain folder, NOT under their own
subdomain folder. This keeps the ddm folder tidy (`inflation.db` +
`juros.db` + `poupanca.db` + `acoes.db` + `focus.db` + `fluxo.db`
side-by-side).

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

CREATE INDEX idx_fluxo_ref_date ON fluxo_observations(ref_date);

CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,   -- always 'fluxo' for this subdomain
    last_date     TEXT,               -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,               -- ISO timestamp of the sync
    row_count     INTEGER             -- number of rows synced
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation` + `ddm/juros`
  + `ddm/poupanca` + `ddm/acoes` + `ddm/focus`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` on
  every connect-for-write.

### Primary key + history

The PK is `ref_date` (one row per trading day). Re-syncing the same day
replaces the row via `INSERT OR REPLACE` — no duplicates. New trading
days (new syncs after market close) accumulate into the historical series.
The /fluxo page exposes ~1 year of trading days, so the DB caps out at
~247 rows (one year of trading days = ~247, since weekends + holidays
are excluded).

## HTTP + parse + store pipeline

The /fluxo page has 1 table (~247 daily rows) on a single HTML document.
The pipeline mirrors `focus` (single HTTP call) with a simpler parser
(no year identification needed — the table has a fixed 6-column shape):

```
fetch_fluxo_page(force)
   │
   ├─ httpx.get(FLUXO_URL, headers=BROWSER_HEADERS, timeout=30)
   │      CloudFront requires full Chrome 127 header set
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock
   └─ return {"status":"ok", "html":..., "synced_at":...}

parse_fluxo_table(html)
   │
   ├─ re.search(r'<table[^>]*class="normal-table"[^>]*>...')
   │      find the single fluxo table
   ├─ extract <tbody>...</tbody>
   ├─ for each <tr><td>...</td>... <td>...</td></tr>:
   │    └─ ref_date       = _parse_br_date(cells[0])    -- "2026-08-19"
   │    └─ estrangeiro    = _parse_br_number(cells[1])  -- -1582.35
   │    └─ institucional  = _parse_br_number(cells[2])  -- 1029.81
   │    └─ pessoa_fisica  = _parse_br_number(cells[3])  -- 42.36
   │    └─ inst_financeira= _parse_br_number(cells[4])  -- 519.49
   │    └─ outros         = _parse_br_number(cells[5])  -- -9.31
   └─ return [{ref_date, estrangeiro, institucional, ...}, ...]

sync_all(force)
   │
   ├─ page = fetch_fluxo_page(force)
   ├─ observations = parse_fluxo_table(page.html)
   ├─ now = datetime.now(timezone.utc).isoformat()
   ├─ last_date = max(ref_date in observations)   # newest trading day
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO fluxo_observations
        (ref_date, estrangeiro, institucional, pessoa_fisica,
         inst_financeira, outros, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        INSERT OR REPLACE INTO sync_state
        (slug, last_date, synced_at, row_count)
        VALUES ('fluxo', ?, ?, ?)
        COMMIT;
```

### Boundary normalizations

| Raw DDM form          | Normalized form   | Field                       |
| --------------------- | ----------------- | --------------------------- |
| `19/08/2026`          | `"2026-08-19"`    | `ref_date`                  |
| `-1.582,35 mi`        | `-1582.35`        | `estrangeiro` / `institucional` / `pessoa_fisica` / `inst_financeira` / `outros` |
| `1.029,81 mi`         | `1029.81`         | same                        |
| `42,36 mi`            | `42.36`           | same                        |
| `-9,31 mi`            | `-9.31`           | same                        |
| `1.234.567,89 mi`     | `1234567.89`      | same                        |
| `0,00 mi`             | `0.0`             | same                        |
| `--`                  | `None`            | any numeric                 |
| `<td class="right nw">42,36 mi</td>` | `42.36` | any numeric (HTML tags stripped first) |

### Differences from `ddm/focus`

| Aspect                | `focus`                                            | `fluxo`                                              |
| --------------------- | -------------------------------------------------- | ---------------------------------------------------- |
| Tables per page       | 4 (one per target year)                            | 1 (single daily table)                               |
| Page rows             | ~48 (4 years × 12 indicators)                      | ~247 (daily trading days, ~1 year)                   |
| Pre-sort              | Indicator order (DDM-controlled)                   | Date DESC (newest first)                             |
| Primary key           | `(year, indicator, ref_date)` — history-aware      | `ref_date` (one row per day)                         |
| Numeric fields        | `four_weeks_ago` / `one_week_ago` / `today` (TEXT) | `estrangeiro` / `institucional` / `pessoa_fisica` / `inst_financeira` / `outros` (REAL) |
| Value storage         | Preserved as PT-BR strings (verbatim)              | Parsed to floats (millions R$)                       |
| Unit                  | Mixed: `%` + `R$` + int                            | Single: millions R$ (with "mi" suffix on source)     |
| Cumulative queries    | None (snapshot, no time series)                    | `monthly_cumulative` + `annual_cumulative`           |
| ref_date granularity  | `YYYY-MM-DD` (sync date — Focus is weekly)         | `YYYY-MM-DD` (trading day — daily)                   |
| Sync concurrency      | Single HTTP call (no executor)                     | Single HTTP call (no executor)                       |
| DB file               | `memory_db/ddm/focus.db`                           | `memory_db/ddm/fluxo.db`                             |

Both sub-domains share the same:
- File layout (6 .py files)
- 5-min fetcher cache + `Semaphore(5)` HTTP concurrency
- `INSERT OR REPLACE` idempotency on the primary key
- DB location (`memory_db/ddm/` shared parent folder)
- 8-mode API surface (sync_all, sync_index, <read-mode>, ..., status)
- Full Chrome 127 browser headers (CloudFront bypass)

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/fluxo/`
via filesystem scan (same pattern as inflation + juros + poupanca +
acoes + focus — any sub-directory with `__init__.py` + `MANIFEST` +
`route()` is picked up automatically). `data_source(domain="ddm",
sub_domain="fluxo", mode="fluxo_data")` resolves to:

```
data_sources.ddm.route(sub_domain="fluxo", mode="fluxo_data")
  └─ fluxo.route(mode="fluxo_data")
        └─ lazy-import query_engine.fluxo_data
        └─ inspect.signature → filter kwargs (limit only)
        └─ return fluxo_data(limit=...)
```

Returns a structured dict: `{status, count, synced_at,
observations: [...]}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).

No new third-party packages required.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.


## Shared infrastructure (`_base/`)

[Phase 3, Commit 1] The shared scaffolding (ddm_data_dir, connect,
ensure_schema, fetcher cache/concurrency/HTTP, sync_engine patterns,
status_reporter scaffold, route() dispatcher) was extracted to
[`data_sources/ddm/_base/`](../../_base/ARCHITECTURE.md). This module
keeps only the source-specific code:

- **catalog.py**: SCHEMA_SQL + URL helpers (+ INDEX_CATALOG for multi-page
  sources). The `db_path` / `connect` / `ensure_schema` module-level
  callables are now thin wrappers over `BaseDDMCatalog` classmethods.
- **fetcher.py**: HTML parser functions (NOT shared — each source has its
  own table shape) + a thin `fetch_<src>_page()` wrapper that calls
  `BaseDDMFetcher.fetch_page()` with the right URL, cache_key, and
  headers (`BOT_HEADERS` for acoes/dividends/inflation/juros/poupanca;
  `BROWSER_HEADERS` for fluxo; `CLOUDFRONT_HEADERS` for focus).
- **sync_engine.py**: per-source config (INSERT SQL, row mapper, B4
  full-refresh flag, last_date computation) + the `sync_index()` entry
  point. The `sync_all()` body delegates to
  `BaseDDMSyncEngine.sync_single_page()` (single-page sources) or
  `BaseDDMSyncEngine.sync_multi_page()` (multi-page sources).
- **status_reporter.py**: source-specific queries in
  `_StatusReporter._build_status_dict()`. The path-check + connect +
  try/except + finally scaffold lives in `BaseDDMStatusReporter.status()`.
- **__init__.py**: MANIFEST (source-specific) + `_MODE_MAP` (a
  `{mode: (module_path, function_name)}` dict) + a
  `route = make_ddm_route(...)` call. The route() dispatcher logic lives
  in `make_ddm_route()`.

The `_base/` package is excluded from sub-domain auto-discovery (the hub
skips directories starting with `_`), so it does NOT register a
sub-domain MANIFEST.

See [`docs/data_sources/ddm/_base/ARCHITECTURE.md`](../../_base/ARCHITECTURE.md)
for the full `_base/` package reference.
