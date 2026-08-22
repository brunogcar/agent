# DDM Acoes — API Reference

Sub-domain: **`acoes`**
Source: <https://www.dadosdemercado.com.br/acoes> (HTML scrape)
Storage: `memory_db/ddm/acoes.db`

## Page shape

The `/acoes` page lists every B3 tradable stock (~380 rows) on a single
server-rendered HTML table (`<table class="normal-table" id="stocks">`).
No pagination, no auth, no JS.

Columns (in order):

| # | Column       | Type    | PT-BR form                 | Normalized             |
| - | ------------ | ------- | -------------------------- | ---------------------- |
| 0 | Ticker       | TEXT    | `PETR4`                    | `ticker` (string)      |
| 1 | Nome         | TEXT    | `Petrobras`                | `name` (string)        |
| 2 | Negocios     | INTEGER | `52.792.400`               | `negocios` (int)       |
| 3 | Ultima (R$)  | REAL    | `44,30`                    | `last_price` (float)   |
| 4 | Variacao     | REAL    | `+2,78%` / `-10,85%`       | `variation` (float)    |

The page is pre-sorted by `Negocios DESC` (most-traded first). DDM does
not expose a "data do pregao" column, so `ref_date` is set to the scrape
date (YYYY-MM-DD).

## 8 modes

### `sync_all`

Fetch the single `/acoes` page, parse the stocks table, and INSERT OR
REPLACE all rows. Idempotent via PK on `ticker`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, rows, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="sync_all")`.

### `sync_index`

Alias for `sync_all` (kept for parity with the other DDM sub-domains;
the acoes page is single-page, not per-index).

- **Params**: `slug` (str, optional — only `acoes` is supported, ignored),
  `force` (bool, default `false`).
- **Returns**: same shape as `sync_all`.

### `stocks`

List all stocks sorted by the specified column + direction. Default sort:
`Negocios DESC` (matches the DDM page order, so the dashboard's default
state mirrors what the user sees on the source page).

- **Params**:
  - `order_by`: one of `ticker`, `name`, `negocios`, `last_price`, `variation`. Default `negocios`.
  - `direction`: `asc` or `desc`. Default `desc`.
  - `limit`: int. 0 = all. Default 0.
- **Returns**: `{status, count, stocks: [{ticker, name, negocios,
  last_price, variation, ref_date, synced_at}, ...]}`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="stocks", params='{"order_by":"variation","direction":"desc"}')`.

### `last`

Get the most recent snapshot for a single ticker.

- **Params**: `ticker` (str, required, e.g. `PETR4`).
- **Returns**: `{status, ticker, name, negocios, last_price, variation,
  ref_date, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="last", params='{"ticker":"PETR4"}')`.

### `search`

Search stocks by ticker or name fragment (case-insensitive LIKE).

- **Params**: `query` (str, required), `limit` (int, default 50).
- **Returns**: same shape as `stocks`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="search", params='{"query":"petro"}')`.

### `summary`

Overview: total stocks, most traded, biggest gainer, biggest loser.

- **Params**: none.
- **Returns**: `{status, total, ref_date, most_traded: {ticker, name,
  negocios}, biggest_gainer: {ticker, name, variation}, biggest_loser:
  {ticker, name, variation}}`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="summary")`.

### `status`

Show `acoes.db` stats: row count + last sync timestamp.

- **Params**: none.
- **Returns**: `{status, path, db_size_kb, total_rows, last_date,
  last_sync, synced_rows}`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="status")`.

### `ticker`

User-facing alias for `last` (same underlying `last_value` query).
Returns the most-recent snapshot for a single ticker — `ticker` is the
more memorable name for callers who don't know the `last` / `last_value`
convention used elsewhere in the codebase.

- **Params**: `ticker` (str, required).
- **Returns**: same shape as `last`.
- **Example**: `data_source(domain="ddm", sub_domain="acoes", mode="ticker", params='{"ticker":"PETR4"}')`.

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary so nothing
downstream ever sees them:

| Raw DDM form      | Normalized form | Field        |
| ----------------- | --------------- | ------------ |
| `52.792.400`      | `52792400`      | `negocios`   |
| `44,30`           | `44.30`         | `last_price` |
| `+2,78%`          | `2.78`          | `variation`  |
| `-10,85%`         | `-10.85`        | `variation`  |
| `--`              | `None`          | any numeric  |

## Concurrency

- Fetcher uses a `Semaphore(5)` to cap in-flight HTTP requests (mirrors the
  `ddm/inflation` + `ddm/juros` pattern).
- A thread-safe in-memory cache (`Lock`-guarded, 5-min TTL) prevents
  re-fetching the same page within the cache window.
- `sync_all` is a single HTTP call (no ThreadPoolExecutor needed) — the
  page is one document, not per-index.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
