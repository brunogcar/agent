# DDM Dividends — API Reference

Sub-domain: **`dividends`**
Source: <https://www.dadosdemercado.com.br/agenda-de-dividendos> (HTML scrape)
Storage: `memory_db/ddm/dividends.db`

## Page shape (single HTML table)

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

- ~200 data rows per sync.
- 2 tipos: `Dividendo` (~149 rows) and `JCP` (~52 rows).
- Value range: R$0.006 to R$7.96 (small per-share amounts, comma decimal).

## 8 modes

### `sync_all`

Sync the entire dividend agenda page (1 HTTP call). Idempotent via
`INSERT OR REPLACE` on `(ticker, record_date, tipo)`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, rows: <int>, synced_at: <iso>}`.
- **Example**: `data_source(domain="ddm", sub_domain="dividends", mode="sync_all")`.

### `sync_index`

Alias for `sync_all` (the dividends page is a single page; slug must be

> **[Phase 4 C2]** The `sync_index` function was deleted from `sync_engine.py`. The `sync_index` mode is now a route-level alias that dispatches directly to `sync_all` (mode-folding in `_MODE_MAP`). The `slug` parameter is silently ignored.
`'dividends'`). Kept for parity with the ddm/inflation/juros/poupanca
`sync_index` signature.

- **Params**: `slug` (str, default `'dividends'`), `force` (bool, default `false`).
- **Returns**: `{status, slug, rows, synced_at}`.

### `dividends`

List all dividends sorted by a column.

- **Params**:
  - `order_by` (str): one of `value` | `ticker` | `tipo` | `record_date` |
    `ex_date` | `payment_date`. Default: `value`.
  - `direction` (str): `desc` | `asc`. Default: `desc`.
  - `limit` (int): max rows. `0` = all. Default: `0`.
- **Returns**: `{status, count, order_by, direction, dividends: [...]}`.
- **Example**:
  ```
  data_source(domain="ddm", sub_domain="dividends", mode="dividends",
              params='{"order_by":"value","direction":"desc"}')
  ```

### `last`

Get the latest dividends for a specific ticker (record_date DESC).

- **Params**: `ticker` (str, required), `limit` (int, default `10`).
- **Returns**: `{status, ticker, count, dividends: [...]}`.
- **Example**:
  ```
  data_source(domain="ddm", sub_domain="dividends", mode="last",
              params='{"ticker":"BBDC3"}')
  ```

### `search`

Search dividends by ticker fragment (case-insensitive LIKE).

- **Params**: `query` (str, required), `limit` (int, default `50`).
- **Returns**: `{status, count, dividends: [...]}`.
- **Example**:
  ```
  data_source(domain="ddm", sub_domain="dividends", mode="search",
              params='{"query":"PETR"}')
  ```

### `ticker`

All dividends for a specific ticker (all dates, all tipos). Convenience
wrapper for `last_value(ticker, limit=0)`.

- **Params**: `ticker` (str, required).
- **Returns**: `{status, ticker, count, dividends: [...]}`.

### `summary`

Overview stats for the dividend agenda.

- **Params**: none.
- **Returns**:
  ```json
  {
    "status": "ok",
    "total_dividends": 201,
    "total_value": 123.45,
    "biggest": {"ticker": "PETR4", "tipo": "JCP", "value": 7.96, "record_date": "2026-06-15"},
    "next_payment_date": "2026-08-03",
    "by_tipo": {"Dividendo": 149, "JCP": 52}
  }
  ```
- **Example**: `data_source(domain="ddm", sub_domain="dividends", mode="summary")`.

### `status`

Show `dividends.db` stats: total rows + per-tipo counts + last sync timestamp.

- **Params**: none.
- **Returns**:
  ```json
  {
    "status": "ok",
    "path": ".../memory_db/ddm/dividends.db",
    "db_size_kb": 24.0,
    "total_rows": 201,
    "by_tipo": {"Dividendo": 149, "JCP": 52},
    "last_date": "2026-12-10",
    "last_sync": "2026-07-25T...",
    "synced_rows": 201
  }
  ```

## Dividend row shape

Every query mode that returns dividends uses the same row dict shape:

```json
{
  "ticker":       "BBDC3",
  "tipo":         "Dividendo",
  "value":        0.017250,
  "record_date":  "2026-07-01",
  "ex_date":      "2026-07-02",
  "payment_date": "2026-08-03"
}
```

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary so nothing
downstream ever sees them:

| Raw DDM form                                | Normalized form   | Field         |
| ------------------------------------------- | ----------------- | ------------- |
| `<a href="/acoes/bbdc3">BBDC3</a>`          | `"BBDC3"`         | ticker        |
| `Dividendo` / `JCP`                         | `"Dividendo"` / `"JCP"` | tipo    |
| `0,017250`                                  | `0.017250`        | value (REAL)  |
| `01/07/2026` (DD/MM/YYYY)                   | `"2026-07-01"`    | record_date / ex_date / payment_date (TEXT) |

DB stores dates as ISO `YYYY-MM-DD`; the dashboard converts to PT-BR
`DD/MM/YYYY` for display via `helpers.format_date()`.

## Concurrency

- Fetcher uses a `Semaphore(5)` to cap in-flight HTTP requests (mirrors
  the `bcb/sgs` + `bcb/focus` + `ddm/inflation/juros/poupanca` pattern).
- `sync_all` is single-threaded (1 page = 1 HTTP call — no need for a
  ThreadPoolExecutor).
- A thread-safe in-memory cache (`Lock`-guarded, 5-min TTL) prevents
  re-fetching the same page within the cache window.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + parse pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
