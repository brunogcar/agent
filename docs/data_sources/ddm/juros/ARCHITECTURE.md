# DDM Juros — Architecture

Sub-domain: **`juros`**
Domain: `ddm`
Mirrors: `data_sources/ddm/inflation/` (file layout + sync pattern, with
        adaptations for the matrix-only juros pages).

## File map (6 files)

```
data_sources/ddm/juros/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # API_BASE, JUROS_CATALOG, SCHEMA_SQL, ddm_data_dir(),
│                        #   db_path(), connect(read_only), ensure_schema,
│                        #   index_url
├── fetcher.py           # fetch_juros_page, parse_matrix_only,
│                        #   flatten_matrix_to_observations (DERIVE pipeline),
│                        #   _parse_br_number, _parse_data_value
├── sync_engine.py       # sync_index(slug, force), sync_all(force)
├── query_engine.py      # juros_history, last_value, monthly_matrix,
│                        #   search, summary
└── status_reporter.py   # status()
```

## Database

`memory_db/ddm/juros.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db`
(`memory_db/ddm/`) - both are per-subdomain DBs under the ddm domain
folder, NOT under their own subdomain folder. This keeps the ddm
folder tidy (`inflation.db` + `juros.db` side-by-side).

### Schema

```sql
CREATE TABLE juros_observations (
    slug          TEXT NOT NULL,
    ref_date      TEXT NOT NULL,        -- 'YYYY-MM' (derived from matrix cell)
    month_value   REAL,                 -- daily rate (% a.a.)
    media_no_ano  REAL,                 -- year-to-date average (% a.a.)
    media_12m     REAL,                 -- rolling 12-month average (% a.a.)
    synced_at     TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX idx_obs_slug ON juros_observations(slug);
CREATE INDEX idx_obs_date ON juros_observations(ref_date);

CREATE TABLE juros_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "selic"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,
    row_count       INTEGER
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` +
  `INSERT OR REPLACE` for catalog rows on every connect-for-write.

## HTTP + parse + derive pipeline

Unlike inflation (which has 2 tables per page), juros pages have only ONE
table (the monthly matrix). The historical series is therefore DERIVED
from the matrix at parse time:

```
fetch_juros_page(slug, force)
   │
   ├─ httpx.get(API_BASE + "/indices/" + slug, headers, timeout=30)
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock
   └─ return {"status":"ok", "slug":..., "html":..., "synced_at":...}

parse_matrix_only(html)
   │
   ├─ re.search(r'<table[^>]*id="index-values"[^>]*>')  # matrix table by id
   ├─ extract <thead><tr><th>...</th></tr></thead>      # header
   ├─ for each <tbody><tr><td>year</td><td data-value=...>...</td></tr>
   │    └─ row[year] = {month_label: _parse_data_value(cell)}
   ├─ filter header months -> canonical 12 (Jan..Dez) - drops "Ano"
   └─ years.sort(reverse=True)                          # newest year first

flatten_matrix_to_observations(matrix)
   │
   ├─ for year ASC, for mon in [Jan..Dez]:               # canonical order
   │    └─ if matrix[year][mon] is not None: flat.append((f"{year}-{mm}", val))
   ├─ flat.sort(key=ref_date)                            # ASC
   │
   └─ for each (ref_date, val) at index i:
        ├─ media_no_ano = mean([flat[j].val for j in [0..i]
        │                      if flat[j].year == flat[i].year])
        └─ media_12m    = mean([flat[j].val for j in [max(0,i-11)..i]])
```

## Sync pipeline

```
sync_all(force)
   │
   ├─ ThreadPoolExecutor(max_workers=3) for each slug in JUROS_CATALOG:
   │    └─ fetch_juros_page(slug, force)
   │       → parse_matrix_only(html)
   │       → flatten_matrix_to_observations(matrix)
   │
   └─ Single connection (write mode):
        for each (slug, observations):
          INSERT OR REPLACE INTO juros_observations (...);
          INSERT OR REPLACE INTO sync_state (slug, last_date, synced_at, row_count);
        COMMIT;
```

Idempotency: re-syncing replaces rows via `INSERT OR REPLACE` on the
`(slug, ref_date)` primary key — no duplicates, no manual upsert logic.

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/juros/`
via filesystem scan (same pattern as inflation - any sub-directory with
`__init__.py` + `MANIFEST` + `route()` is picked up automatically).
`data_source(domain="ddm", sub_domain="juros",
mode="series", params='{"slug":"selic"}')` resolves to:

```
data_sources.ddm.route(sub_domain="juros", mode="series", slug="selic")
  └─ juros.route(mode="series", slug="selic")
        └─ lazy-import query_engine.juros_history
        └─ inspect.signature → filter kwargs
        └─ return juros_history(slug="selic")
```

Returns a structured dict: `{status, slug, name, unit, count, observations}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).
- `concurrent.futures` (stdlib — `ThreadPoolExecutor`).
- `statistics.mean` (stdlib — for media_no_ano + media_12m computation).

No new third-party packages required.

## Differences from `ddm/inflation`

| Aspect                | `inflation`                         | `juros`                                       |
| --------------------- | ----------------------------------- | --------------------------------------------- |
| Tables per page       | 2 (matrix + historical)             | 1 (matrix only)                               |
| "Ano" column          | Yes (year acumulado)                | No (daily rates, not cumulative)              |
| Historical series     | Parsed directly from HTML table 2   | DERIVED from matrix (`flatten_matrix_to_observations`) |
| Numeric fields        | `month_value`, `year_acumulado`, `acumulado_12m` | `month_value`, `media_no_ano`, `media_12m`     |
| Unit                  | `%` (monthly variation)             | `% a.a.` (annualized daily rate)              |
| Indices               | IGP-M, IPCA, INPC                   | Selic, Meta Selic, CDI                        |
| DB file               | `memory_db/ddm/inflation/inflation.db` | `memory_db/ddm/juros.db`                   |

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.


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
