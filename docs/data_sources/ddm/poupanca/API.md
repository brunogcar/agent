# DDM Poupanca — API Reference

Sub-domain: **`poupanca`**
Source: <https://www.dadosdemercado.com.br/indices/poupanca> (HTML scrape)
Storage: `memory_db/ddm/poupanca.db`

## Catalog (1 index)

| slug        | name       | description                                                | unit |
| ----------- | ---------- | ---------------------------------------------------------- | ---- |
| `poupanca`  | Poupanca   | Poupanca - rendimento mensal. Taxa de rendimento da caderneta de poupanca no mes. | %    |

## Why derived (not raw)?

The poupanca page ships ONLY the monthly matrix (`id="index-values"`).
There is **no historical table** on the page and **no "Ano" acumulado
column** (the matrix shows monthly yields, not cumulative values). The
historical series is therefore **derived** at parse time from the matrix
(see `fetcher.flatten_matrix_to_observations`):

| Field                | Derivation                                                          | Matches Google Sheet formula                                          |
| -------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `month_value`        | cell value (monthly yield % for that month)                         | `B:B` (raw)                                                           |
| `acumulado_no_ano`   | SUM of all months in same year UP TO that month (year-to-date)      | `SUM(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`                         |
| `acumulado_12m`      | SUM of the last 12 months INCLUDING the current (rolling window)    | `SUM(FILTER(B:B, A:A<=d, A:A>=d-365))`                                |

For the first 11 months of the catalog (no full 12-month window yet),
`acumulado_12m` uses the available months (NOT None) - this matches the
Google Sheet formula behavior.

### SUM vs AVERAGE (key difference from juros)

Poupanca uses **SUM** for the derived acumulados; juros uses **AVERAGE**.
This is because the poupanca monthly yield is a percentage return (e.g.
0,67% means a 0.67% return that month) - summing monthly returns produces
the cumulative return over the period. Juros monthly cells are daily rates
quoted as annualized % - averaging produces the period-average rate.

This matches the analyst's Google Sheet layout (SUM formulas for poupanca,
AVERAGE formulas for juros).

## 8 modes

### `sync_all`

Sync every index in `POUPANCA_CATALOG` concurrently (`max_workers=3`).
Idempotent via `INSERT OR REPLACE` on `(slug, ref_date)`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, indices_synced, indices_failed, rows_total,
  results: {slug: sync_result}, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="poupanca", mode="sync_all")`.

### `sync_index`

Sync one index (matrix only - historical series is derived at parse time).

- **Params**: `slug` (str, required), `force` (bool, default `false`).
- **Returns**: `{status, slug, rows, synced_at}`.

### `series`

Query derived historical monthly observations for an index (ascending by `ref_date`).

- **Params**: `slug` (str, required), `limit` (int, default `60`).
- **Returns**: `{status, slug, name, unit, count, observations:
  [{ref_date, month_value, acumulado_no_ano, acumulado_12m}, ...]}`.

### `last`

Get the most recent derived observation for an index.

- **Params**: `slug` (str, required).
- **Returns**: `{status, slug, name, unit, ref_date, month_value,
  acumulado_no_ano, acumulado_12m}`.

### `matrix`

Get the monthly matrix (year × month, **NO** "Ano" column) for an index.
Always makes one HTTP call (5-min cache) - the matrix is NOT stored in the DB.

- **Params**: `slug` (str, required).
- **Returns**: `{status, slug, name, unit, years: [int, ...],
  months: ["Jan", ..., "Dez"],
  matrix: {<year_int>: {"Jan": <float|None>, ..., "Dez": <float|None>}}}`.

### `search`

Search `POUPANCA_CATALOG` by slug / name / description fragment
(case-insensitive). Does NOT touch the DB.

- **Params**: `query` (str, required), `limit` (int, default `10`).
- **Returns**: `{status, count, indices: [{slug, name, category, unit}, ...]}`.

### `summary`

Catalog overview (sorted by category then slug). Falls back to the
in-memory `POUPANCA_CATALOG` if the DB has not been synced yet.

- **Params**: none.
- **Returns**: `{status, count, indices: [{slug, name, category,
  description, unit}, ...]}`.

### `status`

Show `poupanca.db` stats: per-index row counts + last sync timestamps.

- **Params**: none.
- **Returns**: `{status, path, db_size_kb, indices_count, total_rows,
  indices: [{slug, name, category, unit, rows, last_ref_date, last_sync,
  synced_rows}, ...]}`.

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary so nothing
downstream ever sees them:

| Raw DDM form      | Normalized form | Field        |
| ----------------- | --------------- | ------------ |
| matrix cell label `Jul` (cell column) | `2026-07` (year + month) | `ref_date`  |
| `0,67`            | `0.67`          | numeric      |
| `-0,12`           | `-0.12`         | numeric      |
| `--`              | `None`          | numeric      |
| `<td data-value="0.67">0,67%</td>` | `0.67` | matrix cell |

## Concurrency

- Fetcher uses a `Semaphore(5)` to cap in-flight HTTP requests (mirrors the
  `bcb/sgs` + `bcb/focus` + `ddm/inflation` + `ddm/juros` pattern).
- `sync_all` uses a `ThreadPoolExecutor(max_workers=3)` (one worker per
  index in the catalog) for the fetch + parse + derive phase; DB writes
  are sequential on a single connection.
- A thread-safe in-memory cache (`Lock`-guarded, 5-min TTL) prevents
  re-fetching the same slug within the cache window.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + derive pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
