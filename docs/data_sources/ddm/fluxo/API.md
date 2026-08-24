# DDM Fluxo — API Reference

Sub-domain: **`fluxo`**
Source: <https://www.dadosdemercado.com.br/fluxo> (HTML scrape, CloudFront-protected)
Storage: `memory_db/ddm/fluxo.db`

## Page shape

The `/fluxo` page lists daily B3 investment flow (net inflow / outflow by
investor type). One table: `<table class="normal-table" id="flow">` with
6 columns. ~247 data rows (daily data, ~1 year of trading days). No
pagination, no auth, no JS.

**CloudFront protection**: the `/fluxo` endpoint is fronted by CloudFront
and rejects bare or identifying bot User-Agents with a 403. The fetcher
sends the full Chrome 127 header set (User-Agent + Accept +
Accept-Language + Connection + Upgrade-Insecure-Requests) to match a real
browser as closely as possible.

Columns (in order):

| # | Column           | Type    | PT-BR form           | Stored as                          |
| - | ---------------- | ------- | -------------------- | ---------------------------------- |
| 0 | Data             | TEXT    | `19/08/2026`         | `ref_date` (YYYY-MM-DD)            |
| 1 | Estrangeiro      | REAL    | `-1.582,35 mi`       | `estrangeiro` (float in millions)  |
| 2 | Institucional    | REAL    | `1.029,81 mi`        | `institucional`                    |
| 3 | Pessoa física    | REAL    | `42,36 mi`           | `pessoa_fisica`                    |
| 4 | Inst. Financeira | REAL    | `519,49 mi`          | `inst_financeira`                  |
| 5 | Outros           | REAL    | `-9,31 mi`           | `outros`                           |

Dates are DESC (newest first). Values use PT-BR formatting with the "mi"
suffix (millions of R$):
- `-1.582,35 mi` = -1582.35 million R$ (outflow)
- `1.029,81 mi` = 1029.81 million R$ (inflow)
- `42,36 mi` = 42.36 million R$
- `-9,31 mi` = -9.31 million R$

Values are **parsed to floats at the fetcher boundary** (unlike ddm/focus
which preserves PT-BR strings verbatim). This is because all 5 value
columns share the same unit (millions R$), so there is no information
loss; and downstream chart + table builders benefit from clean numeric
values (sortability, arithmetic for cumulative monthly/annual views).

## 8 modes

### `sync_all`

Fetch the single `/fluxo` page, parse the table, and INSERT OR REPLACE
all rows. Idempotent via PK on `ref_date`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, rows, last_date, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="sync_all")`.

### `sync_index`

Alias for `sync_all` (kept for parity with the other DDM sub-domains;

> **[Phase 4 C2]** The `sync_index` function was deleted from `sync_engine.py`. The `sync_index` mode is now a route-level alias that dispatches directly to `sync_all` (mode-folding in `_MODE_MAP`). The `slug` parameter is silently ignored.
the fluxo page is single-page, not per-index).

- **Params**: `slug` (str, optional — only `fluxo` is supported, ignored),
  `force` (bool, default `false`).
- **Returns**: same shape as `sync_all`.

### `fluxo_data`

Get all observations (daily data, ascending by date).

- **Params**: `limit` (int, default `0` = all).
- **Returns**: `{status, count, synced_at, observations: [...]}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="fluxo_data")`.

### `last`

Get the latest observation (most recent `ref_date`).

- **Params**: none.
- **Returns**: `{status, ref_date, synced_at, observation: <dict>}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="last")`.

### `search`

Search observations by date fragment (LIKE prefix match).

- **Params**: `query` (str, required, e.g. `2026-08` for all August 2026
  days), `limit` (int, default 50).
- **Returns**: same shape as `fluxo_data`. Sorted DESC (newest first).
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="search", params='{"query":"2026-08"}')`.

### `summary`

Overview stats: row count, date range, last sync.

- **Params**: none.
- **Returns**: `{status, row_count, first_date, last_date, synced_at, sync_rows}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="summary")`.

### `status`

Show `fluxo.db` stats: row count + date range + last sync.

- **Params**: none.
- **Returns**: `{status, path, db_size_kb, total_rows, first_date,
  last_date, last_sync, synced_rows}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="status")`.

### `ticker`

Get one observation by date. The "ticker" name is kept for API parity
with the other DDM modes (acoes / inflation / juros / poupanca / focus
all have a `ticker` mode); in this sub-domain the slot is a date.

- **Params**: `ticker` (str, required). Accepts either `YYYY-MM-DD` or
  `DD/MM/YYYY`.
- **Returns**: `{status, ref_date, observation: <dict>}`.
- **Example**: `data_source(domain="ddm", sub_domain="fluxo", mode="ticker", params='{"ticker":"2026-08-19"}')`.

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary:

| Raw DDM form          | Normalized form   | Field                       |
| --------------------- | ----------------- | --------------------------- |
| `19/08/2026`          | `"2026-08-19"`    | `ref_date`                  |
| `-1.582,35 mi`        | `-1582.35`        | `estrangeiro` / `institucional` / `pessoa_fisica` / `inst_financeira` / `outros` |
| `1.029,81 mi`         | `1029.81`         | same                        |
| `42,36 mi`            | `42.36`           | same                        |
| `-9,31 mi`            | `-9.31`           | same                        |
| `1.234.567,89 mi`     | `1234567.89`      | same                        |
| `0,00 mi`             | `0.0`             | same                        |
| `--`                  | `None`            | any numeric                 |

The `_parse_br_number` helper:
1. Strips the `mi` suffix (case-insensitive).
2. Strips any `R$` prefix + whitespace.
3. Removes ALL dots (PT-BR thousands separator).
4. Replaces comma (PT-BR decimal separator) with dot.
5. Parses as float (preserving the leading minus sign).

The `_parse_br_date` helper converts `DD/MM/YYYY` to `YYYY-MM-DD` (zero-
padded month + day) with strict validation (1-31 for day, 1-12 for month,
1900-2100 for year).

## Concurrency

- Fetcher uses a `Semaphore(5)` to cap in-flight HTTP requests (mirrors
  the other DDM fetchers).
- A thread-safe in-memory cache (`Lock`-guarded, 5-min TTL) prevents
  re-fetching the same page within the cache window.
- `sync_all` is a single HTTP call (no ThreadPoolExecutor needed) — the
  page is one document.

## CloudFront / browser headers

The fetcher sends the full Chrome 127 header set on every request:

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}
```

This mirrors the header set used by the `/boletim-focus` fetcher
(`data_sources/ddm/focus/fetcher.py`) — both endpoints are CloudFront-
protected and require full browser-like headers.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
- [`../DDM.md`](../DDM.md) — DDM domain landing page (covers all 6 sub-domains).
