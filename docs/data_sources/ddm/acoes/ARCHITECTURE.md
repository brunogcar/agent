# DDM Acoes — Architecture

Sub-domain: **`acoes`**
Domain: `ddm`
Mirrors: `data_sources/ddm/inflation/` (file layout + sync pattern, with
        a flat-stocks-table adaptation instead of a per-index historical
        series).

## File map (6 files)

```
data_sources/ddm/acoes/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # ACOES_URL, SCHEMA_SQL, ddm_data_dir(),
│                        #   db_path(), connect(read_only), ensure_schema,
│                        #   acoes_url()
├── fetcher.py           # fetch_acoes_page, parse_stocks_table,
│                        #   _parse_br_number, _parse_br_int,
│                        #   _parse_variation
├── sync_engine.py       # sync_all(force) [sync_index is a mode alias → sync_all]
├── query_engine.py      # stocks_list, stocks (alias), last_value,
│                        #   search, summary
└── status_reporter.py   # status()
```

> **Phase 3 C1 — shared infrastructure:** `catalog.py`, `fetcher.py`, `sync_engine.py`, `status_reporter.py`, and the route dispatcher all subclass the corresponding base classes in [`data_sources/ddm/_base/`](../../_base/ARCHITECTURE.md) (`BaseDDMCatalog`, `BaseDDMFetcher`, `BaseDDMSyncEngine`, `BaseDDMStatusReporter`, `BaseDDMRoute`). The file map above lists what each module exposes to callers — the implementation lives in `_base/`, and this module keeps only source-specific constants + URL/parse helpers. See the "Shared infrastructure (`_base/`)" section at the end of this file for details.

## Database

`memory_db/ddm/acoes.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db` + `juros.db` +
`poupanca.db` (`memory_db/ddm/`) - all 4 are per-subdomain DBs under the
ddm domain folder, NOT under their own subdomain folder. This keeps the
ddm folder tidy (`inflation.db` + `juros.db` + `poupanca.db` +
`acoes.db` side-by-side).

### Schema

```sql
CREATE TABLE stocks (
    ticker        TEXT PRIMARY KEY,     -- 'PETR4'
    name          TEXT,                 -- 'Petrobras'
    negocios      INTEGER,              -- 52792400 (number of trades)
    last_price    REAL,                 -- 44.30 (BRL)
    variation     REAL,                 -- 2.78 (percentage, can be negative)
    ref_date      TEXT,                 -- YYYY-MM-DD (scrape date)
    synced_at     TEXT                  -- ISO timestamp of the sync
);

CREATE INDEX idx_stocks_negocios  ON stocks(negocios);
CREATE INDEX idx_stocks_price     ON stocks(last_price);
CREATE INDEX idx_stocks_variation ON stocks(variation);

CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,     -- always 'acoes' for this subdomain
    last_date     TEXT,                 -- most recent ref_date synced (YYYY-MM-DD)
    synced_at     TEXT,                 -- ISO timestamp of the sync
    row_count     INTEGER               -- number of rows synced
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation` + `ddm/juros`
  + `ddm/poupanca`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` on
  every connect-for-write.

## HTTP + parse + store pipeline

Unlike the other DDM sub-domains (which fetch per-index pages, sometimes
2 tables per page, sometimes with a derived historical series), the acoes
page is a SINGLE page with a SINGLE table. The pipeline is therefore
simpler:

```
fetch_acoes_page(force)
   │
   ├─ httpx.get(API_BASE + "/acoes", headers, timeout=30)
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock
   └─ return {"status":"ok", "html":..., "synced_at":...}

parse_stocks_table(html)
   │
   ├─ re.search(r'<table[^>]*id="stocks"[^>]*>')         # stocks table by id
   ├─ extract <tbody>...</tbody>
   ├─ for each <tr><td>...</td>... <td>...</td></tr>:
   │    └─ ticker    = _strip_html(cells[0])            # strips <a>...</a>
   │    └─ name      = _strip_html(cells[1])
   │    └─ negocios  = _parse_br_int(_strip_html(cells[2]))    # "52.792.400" -> 52792400
   │    └─ last_price= _parse_br_number(_strip_html(cells[3])) # "44,30" -> 44.30
   │    └─ variation = _parse_variation(_strip_html(cells[4])) # "+2,78%" -> 2.78
   └─ return [{"ticker","name","negocios","last_price","variation"}, ...]

sync_all(force)
   │
   ├─ page = fetch_acoes_page(force)
   ├─ stocks = parse_stocks_table(page.html)
   ├─ now = datetime.now(timezone.utc).isoformat()
   ├─ ref_date = today (YYYY-MM-DD, local)
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO stocks
        (ticker, name, negocios, last_price, variation, synced_at, ref_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        INSERT OR REPLACE INTO sync_state
        (slug, last_date, synced_at, row_count)
        VALUES ('acoes', ?, ?, ?)
        COMMIT;
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

## Sync pipeline

```
sync_all(force)
   │
   ├─ fetch_acoes_page(force)
   │      Semaphore(5) caps in-flight HTTP
   │      Lock-guarded 5-min cache
   │
   ├─ parse_stocks_table(html) — regex-based, no BeautifulSoup
   │
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO stocks (...) VALUES (...);
        INSERT OR REPLACE INTO sync_state (...) VALUES (...);
        COMMIT;
```

Idempotency: re-syncing replaces rows via `INSERT OR REPLACE` on the
`ticker` primary key — no duplicates, no manual upsert logic.

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/acoes/`
via filesystem scan (same pattern as inflation + juros + poupanca — any
sub-directory with `__init__.py` + `MANIFEST` + `route()` is picked up
automatically). `data_source(domain="ddm", sub_domain="acoes",
mode="stocks")` resolves to:

```
data_sources.ddm.route(sub_domain="acoes", mode="stocks")
  └─ acoes.route(mode="stocks")
        └─ lazy-import query_engine.stocks_list
        └─ inspect.signature → filter kwargs (order_by, direction, limit)
        └─ return stocks_list(order_by="negocios", direction="desc", limit=0)
```

Returns a structured dict: `{status, count, stocks: [...]}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).

No new third-party packages required.

## Differences from `ddm/inflation` / `ddm/juros` / `ddm/poupanca`

| Aspect                | `inflation` / `juros` / `poupanca`            | `acoes`                                              |
| --------------------- | ---------------------------------------------- | ---------------------------------------------------- |
| Index catalog         | 1-3 indices (slug-keyed)                       | NO catalog — single flat page                        |
| Tables per page       | 1 (matrix only) or 2 (matrix + historical)     | 1 (flat stocks list)                                 |
| Pre-sort              | None (matrix is year x month)                  | Negocios DESC (DDM pre-sorts the page)               |
| Primary key           | `(slug, ref_date)` — multiple obs per index    | `ticker` — single snapshot per ticker                |
| Numeric fields        | `month_value`, `media_no_ano`, `media_12m`, etc. | `negocios`, `last_price`, `variation`               |
| ref_date granularity  | `YYYY-MM` (monthly)                            | `YYYY-MM-DD` (scrape date — DDM doesn't expose a "data do pregao") |
| Sync concurrency      | `ThreadPoolExecutor(max_workers=3)` per index  | Single HTTP call (no executor)                       |
| Variation sign        | Always present (positive/negative)             | Always present (+/- in the source HTML)              |
| DB file               | `memory_db/ddm/inflation.db` / `juros.db` / `poupanca.db` | `memory_db/ddm/acoes.db`                  |
| Catalog category      | `Inflacao` / `Juros` / `Renda Fixa`            | (no catalog — flat list)                             |
| Per-index query modes | `series`, `last`, `matrix`, `search`, `summary` | `stocks`, `last`, `ticker`, `search`, `summary`     |

All 4 sub-domains share the same:
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
