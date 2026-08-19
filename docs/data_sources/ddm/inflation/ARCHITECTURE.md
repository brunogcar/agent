# DDM Inflation — Architecture

Sub-domain: **`inflation`**
Domain: `ddm`
Mirrors: `data_sources/bcb/sgs/` (file layout + sync pattern).

## File map (6 files)

```
data_sources/ddm/inflation/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # API_BASE, INDEX_CATALOG, SCHEMA_SQL, db_path(),
│                        #   connect(read_only), ensure_schema, index_url
├── fetcher.py           # fetch_index_page, parse_historical_table,
│                        #   parse_monthly_matrix, _parse_mes_ano,
│                        #   _parse_br_number, _parse_data_value
├── sync_engine.py       # sync_index(slug, force), sync_all(force)
├── query_engine.py      # index_history, last_value, monthly_matrix,
│                        #   search, summary
└── status_reporter.py   # status()
```

## Database

`memory_db/ddm/inflation/inflation.db` (SQLite, per-subdomain DB pattern).

### Schema

```sql
CREATE TABLE index_observations (
    slug            TEXT NOT NULL,
    ref_date        TEXT NOT NULL,        -- 'YYYY-MM' (normalized from 'Jul/2026')
    month_value     REAL,                 -- variação no mês (%)
    year_acumulado  REAL,                 -- acumulado no ano (%)
    acumulado_12m   REAL,                 -- acumulado 12 meses (%)
    synced_at       TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX idx_obs_slug ON index_observations(slug);
CREATE INDEX idx_obs_date ON index_observations(ref_date);

CREATE TABLE index_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "igp-m"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,
    row_count       INTEGER
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir`).
- Fallback: `memory_db/ddm/inflation/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` +
  `INSERT OR REPLACE` for catalog rows on every connect-for-write.

## HTTP + parse pipeline

```
fetch_index_page(slug, force)
   │
   ├─ httpx.get(API_BASE + "/indices/" + slug, headers, timeout=30)
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock
   └─ return {"status":"ok", "slug":..., "html":..., "synced_at":...}

parse_historical_table(html)
   │
   ├─ re.findall(r"<table[^>]*>[\s\S]*?</table>")   # all tables
   ├─ tables[1]                                       # 2nd table
   ├─ for each <tr>: extract 4 cells, _parse_mes_ano, _parse_br_number
   └─ rows.reverse()                                  # DDM is DESC, we want ASC

parse_monthly_matrix(html)
   │
   ├─ re.search(r'<table[^>]*id="index-values"[^>]*>')  # matrix table by id
   ├─ extract <thead><tr><th>...</th></tr></thead>      # header
   ├─ for each <tbody><tr><td>year</td><td data-value=...>...</td></tr>
   │    └─ row[year] = {month_label: _parse_data_value(cell)}
   └─ years.sort(reverse=True)                          # newest year first
```

## Sync pipeline

```
sync_all(force)
   │
   ├─ ThreadPoolExecutor(max_workers=3) for each slug in INDEX_CATALOG:
   │    └─ fetch_index_page(slug, force) → parse_historical_table(html)
   │
   └─ Single connection (write mode):
        for each (slug, observations):
          INSERT OR REPLACE INTO index_observations (...);
          INSERT OR REPLACE INTO sync_state (slug, last_date, synced_at, row_count);
        COMMIT;
```

Idempotency: re-syncing replaces rows via `INSERT OR REPLACE` on the
`(slug, ref_date)` primary key — no duplicates, no manual upsert logic.

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/inflation/`
via filesystem scan. `data_source(domain="ddm", sub_domain="inflation",
mode="series", params='{"slug":"ipca"}')` resolves to:

```
data_sources.ddm.route(sub_domain="inflation", mode="series", slug="ipca")
  └─ inflation.route(mode="series", slug="ipca")
        └─ lazy-import query_engine.index_history
        └─ inspect.signature → filter kwargs
        └─ return index_history(slug="ipca")
```

Returns a structured dict: `{status, slug, name, unit, count, observations}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).
- `concurrent.futures` (stdlib — `ThreadPoolExecutor`).

No new third-party packages required.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
