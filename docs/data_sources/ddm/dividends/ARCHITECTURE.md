# DDM Dividends — Architecture

Sub-domain: **`dividends`**
Domain: `ddm`
Mirrors: `data_sources/ddm/juros/` + `data_sources/ddm/poupanca/` (file layout +
        sync pattern, adapted for the single-page dividend agenda).

## File map (6 files)

```
data_sources/ddm/dividends/
├── __init__.py          # MANIFEST + route() dispatcher (8 modes)
├── catalog.py           # DIVIDENDS_URL, TIPOS, SORT_KEYS, SCHEMA_SQL,
│                        #   ddm_data_dir(), db_path(), connect(read_only),
│                        #   ensure_schema
├── fetcher.py           # fetch_dividends_page, parse_dividends_table,
│                        #   _parse_br_number, _parse_br_date, _extract_ticker
├── sync_engine.py       # sync_all(force), sync_index(slug, force)
├── query_engine.py      # dividends_list, last_value, search, ticker_history,
│                        #   summary
└── status_reporter.py   # status()
```

> **Phase 3 C1 — shared infrastructure:** `catalog.py`, `fetcher.py`, `sync_engine.py`, `status_reporter.py`, and the route dispatcher all subclass the corresponding base classes in [`data_sources/ddm/_base/`](../../_base/ARCHITECTURE.md) (`BaseDDMCatalog`, `BaseDDMFetcher`, `BaseDDMSyncEngine`, `BaseDDMStatusReporter`, `BaseDDMRoute`). The file map above lists what each module exposes to callers — the implementation lives in `_base/`, and this module keeps only source-specific constants + URL/parse helpers. See the "Shared infrastructure (`_base/`)" section at the end of this file for details.

## Database

`memory_db/ddm/dividends.db` (SQLite, per-subdomain DB pattern).

Lives in the **same parent folder** as `inflation.db` / `juros.db` /
`poupanca.db` (`memory_db/ddm/`) - all 4 per-subdomain DBs sit side-by-side
under the ddm domain folder, NOT under their own subdomain folder. This
keeps the ddm folder tidy.

### Schema

```sql
CREATE TABLE dividends (
    ticker        TEXT NOT NULL,
    tipo          TEXT,
    value         REAL,
    record_date   TEXT,
    ex_date       TEXT,
    payment_date  TEXT,
    synced_at     TEXT,
    PRIMARY KEY (ticker, record_date, tipo)
);

CREATE INDEX idx_div_ticker ON dividends(ticker);
CREATE INDEX idx_div_record ON dividends(record_date);
CREATE INDEX idx_div_ex     ON dividends(ex_date);
CREATE INDEX idx_div_pay    ON dividends(payment_date);
CREATE INDEX idx_div_tipo   ON dividends(tipo);

CREATE TABLE sync_state (
    slug          TEXT PRIMARY KEY,
    last_date     TEXT,
    synced_at     TEXT,
    row_count     INTEGER
);
```

### Layout

- `memory_root` is read from `core.config.cfg.memory_root` when available
  (mirrors `bcb/sgs/catalog.bcb_data_dir` + `ddm/inflation/juros/poupanca`).
- Fallback: `memory_db/ddm/` relative to cwd.
- `ensure_schema()` is idempotent — runs `CREATE TABLE IF NOT EXISTS` on
  every connect-for-write.

## HTTP + parse pipeline

The dividend agenda is a single HTML page with a single table:

```
fetch_dividends_page(force)
   │
   ├─ httpx.get(DIVIDENDS_URL, headers, timeout=30)
   ├─ raise_for_status()
   ├─ cache.set(cache_key, result, ttl=300)   # thread-safe Lock, single key
   └─ return {"status":"ok", "html":..., "synced_at":...}

parse_dividends_table(html)
   │
   ├─ re.search(r'<table[^>]*class="[^"]*normal-table[^"]*"[^>]*>')
   │    └─ fallback: first <table> on the page
   ├─ for each <tbody><tr><td>...x6...</tr>
   │    ├─ _extract_ticker(cells[0])      # <a> tag inner text fallback to stripped HTML
   │    ├─ _strip_html(cells[1])          # Tipo (Dividendo | JCP)
   │    ├─ _parse_br_number(cells[2])     # "0,017250" -> 0.017250
   │    ├─ _parse_br_date(cells[3])       # "01/07/2026" -> "2026-07-01"
   │    ├─ _parse_br_date(cells[4])       # "02/07/2026" -> "2026-07-02"
   │    └─ _parse_br_date(cells[5])       # "03/08/2026" -> "2026-08-03"
   └─ return [{ticker, tipo, value, record_date, ex_date, payment_date}, ...]
```

### Page shape (confirmed)

```html
<table class="normal-table">
  <thead><tr>
    <th>Codigo</th><th>Tipo</th><th>Valor (R$)</th>
    <th>Registro</th><th>Ex</th><th>Pagamento</th>
  </tr></thead>
  <tbody>
    <tr>
      <td><strong><a href="/acoes/bbdc3">BBDC3</a></strong></td>
      <td>Dividendo</td>
      <td>0,017250</td>
      <td>01/07/2026</td>
      <td>02/07/2026</td>
      <td>03/08/2026</td>
    </tr>
    ...
  </tbody>
</table>
```

## Sync pipeline

```
sync_all(force)
   │
   ├─ fetch_dividends_page(force)
   ├─ parse_dividends_table(html)
   │
   └─ Single connection (write mode):
        INSERT OR REPLACE INTO dividends
          (ticker, tipo, value, record_date, ex_date, payment_date, synced_at)
          VALUES (?, ?, ?, ?, ?, ?, ?)   # one row per parsed dividend
        INSERT OR REPLACE INTO sync_state
          (slug, last_date, synced_at, row_count)
          VALUES ('dividends', MAX(record_date), NOW, len(rows))
        COMMIT;
```

Idempotency: re-syncing replaces rows via `INSERT OR REPLACE` on the
`(ticker, record_date, tipo)` primary key — no duplicates.

## Routing

`data_sources/ddm/__init__.py` auto-discovers `data_sources/ddm/dividends/`
via filesystem scan (same pattern as inflation/juros/poupanca - any sub-
directory with `__init__.py` + `MANIFEST` + `route()` is picked up
automatically). `data_source(domain="ddm", sub_domain="dividends",
mode="dividends", params='{"order_by":"value","direction":"desc"}')`
resolves to:

```
data_sources.ddm.route(sub_domain="dividends", mode="dividends",
                       order_by="value", direction="desc")
  └─ dividends.route(mode="dividends", order_by="value", direction="desc")
        └─ lazy-import query_engine.dividends_list
        └─ inspect.signature → filter kwargs
        └─ return dividends_list(order_by="value", direction="desc")
```

Returns a structured dict:
`{status, count, order_by, direction, dividends: [...]}`.

## Dependencies

- `httpx` (already a project dependency).
- `sqlite3` (stdlib).
- `re` (stdlib — no BeautifulSoup, no lxml).

No new third-party packages required.

## Differences from `ddm/juros` + `ddm/poupanca`

| Aspect                | `juros` / `poupanca`                          | `dividends`                                    |
| --------------------- | --------------------------------------------- | ---------------------------------------------- |
| Page shape            | Per-index page (3 pages)                      | Single agenda page                             |
| Table class           | `id="index-values"` (matrix)                  | `class="normal-table"` (rows)                  |
| Tables per page       | 1 (matrix only - historical derived)          | 1 (rows only - no derivation needed)           |
| Numeric fields        | `month_value`, `media_no_ano`, `media_12m`    | `value` (R$)                                   |
| Date fields           | single `ref_date` (YYYY-MM)                   | `record_date`, `ex_date`, `payment_date` (YYYY-MM-DD) |
| Primary key           | `(slug, ref_date)`                            | `(ticker, record_date, tipo)`                  |
| Catalog               | `JUROS_CATALOG` (3 indices) / `POUPANCA_CATALOG` (1) | no catalog (rows fetched as-is)         |
| Index count           | 3 / 1                                         | ~200 rows (~149 Dividendo + ~52 JCP)           |
| Unit                  | `% a.a.` (juros) / `%` (poupanca)             | `R$` (REAL)                                    |
| DB file               | `memory_db/ddm/juros.db` / `poupanca.db`      | `memory_db/ddm/dividends.db`                   |

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
