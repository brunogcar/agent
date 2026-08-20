# DDM Poupanca — Architecture

Sub-domain: **`poupanca`**
Domain: `ddm`
Mirrors: `data_sources/ddm/juros/` (file layout + sync pattern, with
        adaptations for the SUM-derived acumulados).

## File map (6 files)

```
data_sources/ddm/poupanca/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # API_BASE, POUPANCA_CATALOG, SCHEMA_SQL, ddm_data_dir(),
│                        #   db_path(), connect(read_only), ensure_schema,
│                        #   index_url
├── fetcher.py           # fetch_poupanca_page, parse_matrix_only,
│                        #   flatten_matrix_to_observations (DERIVE pipeline),
│                        #   _parse_br_number, _parse_data_value
├── sync_engine.py       # sync_index(slug, force), sync_all(force)
├── query_engine.py      # poupanca_history, last_value, monthly_matrix,
│                        #   search, summary
└── status_reporter.py   # status()
```

## Database

`memory_db/ddm/poupanca.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db` + `juros.db`
(`memory_db/ddm/`) - all are per-subdomain DBs under the ddm domain
folder, NOT under their own subdomain folder. This keeps the ddm
folder tidy (`inflation.db` + `juros.db` + `poupanca.db` side-by-side).

### Schema

```sql
CREATE TABLE poupanca_observations (
    slug             TEXT NOT NULL,
    ref_date         TEXT NOT NULL,        -- 'YYYY-MM' (derived from matrix cell)
    month_value      REAL,                 -- monthly yield (%)
    acumulado_no_ano REAL,                 -- year-to-date SUM (%)
    acumulado_12m    REAL,                 -- rolling 12-month SUM (%)
    synced_at        TEXT,
    PRIMARY KEY (slug, ref_date)
);

CREATE INDEX idx_obs_slug ON poupanca_observations(slug);
CREATE INDEX idx_obs_date ON poupanca_observations(ref_date);

CREATE TABLE poupanca_catalog (
    slug            TEXT PRIMARY KEY,
    name            TEXT,
    category        TEXT,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE sync_state (
    slug            TEXT PRIMARY KEY,     -- e.g. "poupanca"
    last_date       TEXT,                 -- most recent ref_date synced (YYYY-MM)
    synced_at       TEXT,
    row_count       INTEGER
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation` + `ddm/juros`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` +
  `INSERT OR REPLACE` for catalog rows on every connect-for-write.

## HTTP + parse + derive pipeline

Like juros, the poupanca page has only ONE table (the monthly matrix).
The historical series is therefore DERIVED from the matrix at parse time:

```
fetch_poupanca_page(slug, force)
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
        ├─ acumulado_no_ano = SUM([flat[j].val for j in [0..i]
        │                       if flat[j].year == flat[i].year])
        └─ acumulado_12m    = SUM([flat[j].val for j in [max(0,i-11)..i]])
```

### SUM vs AVERAGE (KEY difference from juros)

Poupanca uses **SUM** for the derived acumulados; juros uses **AVERAGE**.

| Field               | Poupanca (SUM)                                                | Juros (AVERAGE)                                          |
| ------------------- | ------------------------------------------------------------- | -------------------------------------------------------- |
| `acumulado_no_ano`  | `SUM(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`                 | `AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`        |
| `acumulado_12m`     | `SUM(FILTER(B:B, A:A<=d, A:A>=d-365))`                        | `AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))`               |

**Rationale**: poupanca monthly yield is a **percentage return** (e.g. 0,67%
means a 0.67% return that month). Summing monthly returns produces the
cumulative return over the period (e.g. 12 months × ~0.6%/month ≈ 7.2%/year).
Juros monthly cells are daily rates quoted as **annualized %** - averaging
produces the period-average annualized rate.

This matches the analyst's Google Sheet layout (SUM formulas for poupanca,
AVERAGE formulas for juros).

## Sync pipeline

```
sync_all(force)
   │
   ├─ ThreadPoolExecutor(max_workers=3) for each slug in POUPANCA_CATALOG:
   │    └─ fetch_poupanca_page(slug, force)
   │       → parse_matrix_only(html)
   │       → flatten_matrix_to_observations(matrix)
   │
   └─ Single connection (write mode):
        for each (slug, observations):
          INSERT OR REPLACE INTO poupanca_observations (...);
          INSERT OR REPLACE INTO sync_state (slug, last_date, synced_at, row_count);
        COMMIT;
```

Idempotency: re-syncing replaces rows via `INSERT OR REPLACE` on the
`(slug, ref_date)` primary key — no duplicates, no manual upsert logic.

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/poupanca/`
via filesystem scan (same pattern as inflation + juros - any sub-directory
with `__init__.py` + `MANIFEST` + `route()` is picked up automatically).
`data_source(domain="ddm", sub_domain="poupanca",
mode="series", params='{"slug":"poupanca"}')` resolves to:

```
data_sources.ddm.route(sub_domain="poupanca", mode="series", slug="poupanca")
  └─ poupanca.route(mode="series", slug="poupanca")
        └─ lazy-import query_engine.poupanca_history
        └─ inspect.signature → filter kwargs
        └─ return poupanca_history(slug="poupanca")
```

Returns a structured dict: `{status, slug, name, unit, count, observations}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).
- `concurrent.futures` (stdlib — `ThreadPoolExecutor`).
- (No `statistics.mean` - poupanca uses SUM, not AVERAGE.)

No new third-party packages required.

## Differences from `ddm/juros`

| Aspect                | `juros`                                       | `poupanca`                                            |
| --------------------- | --------------------------------------------- | ----------------------------------------------------- |
| Derivation            | AVERAGE (mean of monthly cells)               | SUM (sum of monthly cells)                            |
| Numeric fields        | `month_value`, `media_no_ano`, `media_12m`    | `month_value`, `acumulado_no_ano`, `acumulado_12m`    |
| Unit                  | `% a.a.` (annualized daily rate)              | `%` (monthly yield)                                   |
| Indices               | Selic, Meta Selic, CDI (3 indices)            | Poupanca (1 index)                                    |
| DB file               | `memory_db/ddm/juros.db`                      | `memory_db/ddm/poupanca.db`                           |
| Catalog category      | `Juros`                                       | `Renda Fixa`                                          |
| Tables per page       | 1 (matrix only)                               | 1 (matrix only)                                       |
| "Ano" column          | No                                            | No                                                    |
| Historical series     | DERIVED from matrix (AVERAGE)                 | DERIVED from matrix (SUM)                             |

Both sub-domains share the same:
- File layout (6 .py files)
- 5-min fetcher cache + `Semaphore(5)` HTTP concurrency
- `ThreadPoolExecutor(max_workers=3)` sync concurrency
- `(slug, ref_date)` primary key + `INSERT OR REPLACE` idempotency
- DB location (`memory_db/ddm/` shared parent folder)
- 8-mode API surface (sync_all, sync_index, series, last, matrix, search,
  summary, status)

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
