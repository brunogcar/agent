# DDM Focus — Architecture

Sub-domain: **`focus`**
Domain: `ddm`
Mirrors: `data_sources/ddm/acoes/` (file layout + sync pattern, adapted
        for the 4-tables-per-page Boletim Focus layout instead of the
        single flat stocks list).

## File map (6 files)

```
data_sources/ddm/focus/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # FOCUS_URL, SCHEMA_SQL, ddm_data_dir(),
│                        #   db_path(), connect(read_only), ensure_schema,
│                        #   focus_url()
├── fetcher.py           # fetch_focus_page (full Chrome 127 browser
│                        #   headers for CloudFront), parse_focus_tables,
│                        #   _parse_int, _normalize_comparison,
│                        #   _find_year_for_table, _strip_html
├── sync_engine.py       # sync_all(force), sync_index(slug, force)
├── query_engine.py      # focus_by_year, focus_by_indicator, last_value,
│                        #   search, summary, all_data
└── status_reporter.py   # status()
```

## Database

`memory_db/ddm/focus.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db` + `juros.db` +
`poupanca.db` + `acoes.db` (`memory_db/ddm/`) - all 5 are per-subdomain
DBs under the ddm domain folder, NOT under their own subdomain folder.
This keeps the ddm folder tidy (`inflation.db` + `juros.db` +
`poupanca.db` + `acoes.db` + `focus.db` side-by-side).

### Schema

```sql
CREATE TABLE focus_observations (
    year            INTEGER NOT NULL,
    indicator       TEXT NOT NULL,
    four_weeks_ago  TEXT,              -- "5,151%" or "R$ 5,200" (verbatim)
    one_week_ago    TEXT,              -- same
    today           TEXT,              -- same
    comparison      TEXT,              -- "up" / "down" / "flat" / ""
    respondents     INTEGER,           -- 149 (or NULL for missing)
    ref_date        TEXT,              -- YYYY-MM-DD (sync date)
    synced_at       TEXT,              -- ISO timestamp of the sync
    PRIMARY KEY (year, indicator, ref_date)
);

CREATE INDEX idx_focus_year      ON focus_observations(year);
CREATE INDEX idx_focus_indicator ON focus_observations(indicator);
CREATE INDEX idx_focus_ref_date  ON focus_observations(ref_date);

CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,   -- always 'focus' for this subdomain
    last_date     TEXT,               -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,               -- ISO timestamp of the sync
    row_count     INTEGER             -- number of rows synced
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation` + `ddm/juros`
  + `ddm/poupanca` + `ddm/acoes`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` on
  every connect-for-write.

### Primary key + history

The PK is `(year, indicator, ref_date)`. This is intentionally NOT
`year, indicator` alone because **Focus is published weekly** — re-syncing
the same (year, indicator) on a different day produces a different
`ref_date` and therefore a new row. Earlier snapshots are preserved so
consumers can query the history of focus expectations over time.

If you only want the latest snapshot, use the `all_data()` /
`focus_data()` query modes — they filter to the latest `ref_date`
automatically.

## HTTP + parse + store pipeline

The Boletim Focus page has 4 tables (one per year) on a single HTML
document. The pipeline is therefore similar to `acoes` (single HTTP call)
but with a more complex parser:

```
fetch_focus_page(force)
   │
   ├─ httpx.get(FOCUS_URL, headers=BROWSER_HEADERS, timeout=30)
   │      CloudFront requires full Chrome 127 header set
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock
   └─ return {"status":"ok", "html":..., "synced_at":...}

parse_focus_tables(html)
   │
   ├─ re.finditer(r'<table[^>]*class="normal-table"[^>]*>...')
   │      find all 4 yearly tables
   ├─ for each table:
   │    └─ year = _find_year_for_table(html, table_start)
   │         walk backwards to nearest <h2>/<h3> containing 20XX
   │    └─ for each <tr><td>...</td>... <td>...</td></tr>:
   │         └─ indicator    = _strip_html(cells[0])  -- "IPCA"
   │         └─ four_weeks_ago = _strip_html(cells[1]) -- "5,151%"
   │         └─ one_week_ago   = _strip_html(cells[2]) -- "5,150%"
   │         └─ today          = _strip_html(cells[3]) -- "5,200%"
   │         └─ comparison = _normalize_comparison(cells[4]) -- "up"
   │         └─ respondents = _parse_int(_strip_html(cells[5])) -- 149
   └─ return [{year, indicator, four_weeks_ago, one_week_ago, today,
              comparison, respondents}, ...]

sync_all(force)
   │
   ├─ page = fetch_focus_page(force)
   ├─ observations = parse_focus_tables(page.html)
   ├─ now = datetime.now(timezone.utc).isoformat()
   ├─ ref_date = today (YYYY-MM-DD, local)
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO focus_observations
        (year, indicator, four_weeks_ago, one_week_ago, today,
         comparison, respondents, ref_date, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        INSERT OR REPLACE INTO sync_state
        (slug, last_date, synced_at, row_count)
        VALUES ('focus', ?, ?, ?)
        COMMIT;
```

### Boundary normalizations

| Raw DDM form                  | Normalized form      | Field             |
| ----------------------------- | -------------------- | ----------------- |
| `5,151%`                      | `"5,151%"`           | `four_weeks_ago` / `one_week_ago` / `today` |
| `R$ 5,200`                    | `"R$ 5,200"`         | same              |
| `149`                         | `149`                | `respondents`     |
| `149 resp.`                   | `149`                | `respondents`     |
| `▲` (U+25B2)                  | `"up"`               | `comparison`      |
| `▼` (U+25BC)                  | `"down"`             | `comparison`      |
| `=` (U+003D)                  | `"flat"`             | `comparison`      |
| `Alta` / `Baixa` / `Estavel`  | `"up"` / `"down"` / `"flat"` | `comparison` |
| `--`                          | `None`               | `respondents`     |
| `<a href="...">IPCA</a>`      | `IPCA`               | `indicator`       |

## Sync pipeline

```
sync_all(force)
   │
   ├─ fetch_focus_page(force)
   │      Semaphore(5) caps in-flight HTTP
   │      Lock-guarded 5-min cache
   │      Full Chrome 127 browser headers (CloudFront bypass)
   │
   ├─ parse_focus_tables(html) — regex-based, no BeautifulSoup
   │      Per-table year identification from preceding heading
   │
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO focus_observations (...) VALUES (...);
        INSERT OR REPLACE INTO sync_state (...) VALUES (...);
        COMMIT;
```

Idempotency: re-syncing the same day replaces rows via `INSERT OR REPLACE`
on the `(year, indicator, ref_date)` primary key — no duplicates, no
manual upsert logic. Different `ref_date`s accumulate into a history
series (Focus is weekly, so consecutive syncs on different days yield
different `ref_date`s and the history grows).

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/focus/`
via filesystem scan (same pattern as inflation + juros + poupanca +
acoes — any sub-directory with `__init__.py` + `MANIFEST` + `route()` is
picked up automatically). `data_source(domain="ddm",
sub_domain="focus", mode="focus_data")` resolves to:

```
data_sources.ddm.route(sub_domain="focus", mode="focus_data")
  └─ focus.route(mode="focus_data")
        └─ lazy-import query_engine.all_data
        └─ inspect.signature → filter kwargs (none)
        └─ return all_data()
```

Returns a structured dict: `{status, ref_date, synced_at, count,
observations: [...]}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).

No new third-party packages required.

## Differences from `ddm/acoes` / `ddm/inflation` / `ddm/juros` / `ddm/poupanca`

| Aspect                | `acoes` / `inflation` / `juros` / `poupanca`  | `focus`                                            |
| --------------------- | --------------------------------------------- | -------------------------------------------------- |
| Index catalog         | 1-3 indices (slug-keyed) or none (acoes)      | NO catalog — 4 year-tables on one page             |
| Tables per page       | 1 (matrix only) or 2 (matrix + historical) or 1 (acoes flat) | 4 (one per target year)              |
| Pre-sort              | None (or Negocios DESC for acoes)             | Indicator order (DDM-controlled)                   |
| Primary key           | `(slug, ref_date)` or `ticker` (acoes)        | `(year, indicator, ref_date)` — history-aware      |
| Numeric fields        | `month_value`, `media_no_ano`, etc.           | `four_weeks_ago`, `one_week_ago`, `today` (TEXT)   |
| Comparison column     | None                                          | Yes (`comparison`: "up"/"down"/"flat"/"")          |
| Respondents column    | None                                          | Yes (`respondents`: int count)                     |
| ref_date granularity  | `YYYY-MM` (monthly) or `YYYY-MM-DD` (acoes)   | `YYYY-MM-DD` (sync date — Focus is weekly)         |
| Sync concurrency      | `ThreadPoolExecutor(max_workers=3)` per index | Single HTTP call (no executor)                     |
| DB file               | `memory_db/ddm/{acoes,inflation,juros,poupanca}.db` | `memory_db/ddm/focus.db`                  |
| Per-index query modes | `series`, `last`, `matrix`, etc.              | `focus_data`, `last`, `indicator`, `search`, ...   |
| Browser headers       | Minimal (UA + Accept)                          | Full Chrome 127 set (CloudFront WAF bypass)       |
| Value storage         | Normalized to float / int                      | Preserved as PT-BR strings (verbatim)              |

All 5 sub-domains share the same:
- File layout (6 .py files)
- 5-min fetcher cache + `Semaphore(5)` HTTP concurrency
- `INSERT OR REPLACE` idempotency on the primary key
- DB location (`memory_db/ddm/` shared parent folder)
- 8-mode API surface (sync_all, sync_index, <read-mode>, ..., status)

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
