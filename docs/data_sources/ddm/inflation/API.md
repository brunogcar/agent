# DDM Inflation — API Reference

Sub-domain: **`inflation`**
Source: <https://www.dadosdemercado.com.br/indices/{slug}> (HTML scrape)
Storage: `memory_db/ddm/inflation/inflation.db`

## Catalog (3 indices)

| slug    | name  | description                                                  | unit |
| ------- | ----- | ------------------------------------------------------------ | ---- |
| `igp-m` | IGP-M | Índice Geral de Preços - Mercado (FGV). Variação mensal %.   | %    |
| `ipca`  | IPCA  | Índice Nacional de Preços ao Consumidor Amplo (IBGE).        | %    |
| `inpc`  | INPC  | Índice Nacional de Preços ao Consumidor (IBGE).              | %    |

## 8 modes

### `sync_all`

Sync every index in `INDEX_CATALOG` concurrently (`max_workers=3`).
Idempotent via `INSERT OR REPLACE` on `(slug, ref_date)`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, indices_synced, indices_failed, rows_total,
  results: {slug: sync_result}, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="inflation", mode="sync_all")`.

### `sync_index`

Sync one index (full HTML history).

- **Params**: `slug` (str, required), `force` (bool, default `false`).
- **Returns**: `{status, slug, rows, synced_at}`.

### `series`

Query historical monthly observations for an index (ascending by `ref_date`).

- **Params**: `slug` (str, required), `limit` (int, default `60`).
- **Returns**: `{status, slug, name, unit, count, observations:
  [{ref_date, month_value, year_acumulado, acumulado_12m}, ...]}`.

### `last`

Get the most recent observation for an index.

- **Params**: `slug` (str, required).
- **Returns**: `{status, slug, name, unit, ref_date, month_value,
  year_acumulado, acumulado_12m}`.

### `matrix`

Get the monthly matrix (year × month) for an index. Always makes one HTTP
call (5-min cache) — the matrix is NOT stored in the DB.

- **Params**: `slug` (str, required).
- **Returns**: `{status, slug, name, unit, years: [int, ...],
  months: ["Jan", ..., "Dez", "Ano"],
  matrix: {<year_int>: {"Jan": <float|None>, ..., "Ano": <float|None>}}}`.

### `search`

Search `INDEX_CATALOG` by slug / name / description fragment
(case-insensitive). Does NOT touch the DB.

- **Params**: `query` (str, required), `limit` (int, default `10`).
- **Returns**: `{status, count, indices: [{slug, name, category, unit}, ...]}`.

### `summary`

Catalog overview (sorted by category then slug). Falls back to the
in-memory `INDEX_CATALOG` if the DB has not been synced yet.

- **Params**: none.
- **Returns**: `{status, count, indices: [{slug, name, category,
  description, unit}, ...]}`.

### `status`

Show `inflation.db` stats: per-index row counts + last sync timestamps.

- **Params**: none.
- **Returns**: `{status, path, db_size_kb, indices_count, total_rows,
  indices: [{slug, name, category, unit, rows, last_ref_date, last_sync,
  synced_rows}, ...]}`.

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary so nothing
downstream ever sees them:

| Raw DDM form      | Normalized form | Field        |
| ----------------- | --------------- | ------------ |
| `Jul/2026`        | `2026-07`       | `ref_date`   |
| `0,41`            | `0.41`          | numeric      |
| `-1,16`           | `-1.16`         | numeric      |
| `--`              | `None`          | numeric      |
| `<td data-value="0.41">0,41%</td>` | `0.41` | matrix cell |

## Concurrency

- Fetcher uses a `Semaphore(5)` to cap in-flight HTTP requests (mirrors the
  `bcb/sgs` + `bcb/focus` pattern).
- `sync_all` uses a `ThreadPoolExecutor(max_workers=3)` (one worker per
  index in the catalog) for the fetch + parse phase; DB writes are
  sequential on a single connection.
- A thread-safe in-memory cache (`Lock`-guarded, 5-min TTL) prevents
  re-fetching the same slug within the cache window.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
