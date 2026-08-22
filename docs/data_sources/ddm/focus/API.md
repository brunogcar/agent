# DDM Focus — API Reference

Sub-domain: **`focus`**
Source: <https://www.dadosdemercado.com.br/boletim-focus> (HTML scrape, CloudFront-protected)
Storage: `memory_db/ddm/focus.db`

## Page shape

The `/boletim-focus` page lists market expectations for the next 4 target
years (2026, 2027, 2028, 2029). Each year has its own HTML table
(`<table class="normal-table">`), preceded by a heading (`<h2>` or
`<h3>`) containing the year. No pagination, no auth, no JS.

**CloudFront protection**: the `/boletim-focus` endpoint is fronted by
CloudFront and rejects bare or identifying bot User-Agents with a 403.
The fetcher sends the full Chrome 127 header set (User-Agent + Accept +
Accept-Language + Accept-Encoding + Connection + Upgrade-Insecure-Requests)
to match a real browser as closely as possible. This is more comprehensive
than the headers used by the `/acoes` and `/indices` endpoints.

Columns (in order, per table):

| # | Column         | Type    | PT-BR form                          | Stored as                            |
| - | -------------- | ------- | ----------------------------------- | ------------------------------------ |
| 0 | Indicador      | TEXT    | `IPCA`                              | `indicator` (string)                 |
| 1 | Ha 4 semanas   | TEXT    | `5,151%` / `R$ 5,200`               | `four_weeks_ago` (string, verbatim)  |
| 2 | 1 sem          | TEXT    | `5,150%` / `R$ 5,250`               | `one_week_ago` (string, verbatim)    |
| 3 | Hoje           | TEXT    | `5,200%` / `R$ 5,180`               | `today` (string, verbatim)           |
| 4 | Comp.          | TEXT    | `▲` / `▼` / `=`                     | `comparison` ("up"/"down"/"flat"/"") |
| 5 | Resp.          | INTEGER | `149`                               | `respondents` (int)                  |

DDM publishes 12 indicators per year (sometimes 13 when "IPCA Adm" is
split into its own row):

```
IPCA, PIB Total, Cambio, Selic, IGP-M, IPCA Adm,
Conta corrente, Balanca comercial, Investimento direto no pais,
Divida liquida setor pub, Resultado primario, Resultado nominal.
```

Values are stored as **PT-BR strings verbatim** ("5,151%", "R$ 5,200")
to preserve the source format. The dashboard renders them as-is; only
the chart builder parses them into floats.

The comparison column is normalized to one of `"up"` / `"down"` /
`"flat"` / `""` at the fetcher boundary (raw `▲` / `▼` / `=` glyphs are
not stored). The dashboard re-renders the glyphs and applies colors
(green / red / gray).

## 8 modes

### `sync_all`

Fetch the single `/boletim-focus` page, parse the 4 yearly tables, and
INSERT OR REPLACE all rows. Idempotent via PK on `(year, indicator,
ref_date)`.

- **Params**: `force` (bool, default `false`) — re-fetch even if recently synced.
- **Returns**: `{status, rows, ref_date, synced_at}`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="sync_all")`.

### `sync_index`

Alias for `sync_all` (kept for parity with the other DDM sub-domains;
the focus page is single-page, not per-index).

- **Params**: `slug` (str, optional — only `focus` is supported, ignored),
  `force` (bool, default `false`).
- **Returns**: same shape as `sync_all`.

### `focus_data`

Get all observations for the latest sync (full snapshot, 4 years × 12
indicators = ~48 rows). Rows are sorted by year ASC then indicator ASC.

- **Params**: none.
- **Returns**: `{status, ref_date, synced_at, count, observations: [...]}`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="focus_data")`.

### `last`

Get the latest sync metadata + all observations (alias for `focus_data`).

- **Params**: none.
- **Returns**: same shape as `focus_data`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="last")`.

### `search`

Search observations by indicator name fragment (case-insensitive LIKE).
Searches the latest ref_date only.

- **Params**: `query` (str, required), `limit` (int, default 50).
- **Returns**: same shape as `focus_data`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="search", params='{"query":"IPCA"}')`.

### `summary`

Overview: years covered, distinct indicators, last sync.

- **Params**: none.
- **Returns**: `{status, ref_date, synced_at, years: [int, ...],
  indicators: [str, ...], year_count, indicator_count, row_count}`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="summary")`.

### `status`

Show `focus.db` stats: row count + year/indicator counts + last sync.

- **Params**: none.
- **Returns**: `{status, path, db_size_kb, total_rows, year_count,
  indicator_count, years, indicators, last_date, last_sync, synced_rows}`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="status")`.

### `indicator`

Get all years for a given indicator (latest sync only).

- **Params**: `indicator` (str, required, e.g. `IPCA`).
- **Returns**: `{status, indicator, ref_date, count, observations: [...]}`.
- **Example**: `data_source(domain="ddm", sub_domain="focus", mode="indicator", params='{"indicator":"Selic"}')`.

## Boundary normalizations

All raw DDM strings are normalized at the fetcher boundary:

| Raw DDM form    | Normalized form | Field             |
| --------------- | --------------- | ----------------- |
| `5,151%`        | `"5,151%"`      | `four_weeks_ago` / `one_week_ago` / `today` |
| `R$ 5,200`      | `"R$ 5,200"`    | `four_weeks_ago` / `one_week_ago` / `today` |
| `149`           | `149`           | `respondents`     |
| `▲`             | `"up"`          | `comparison`      |
| `▼`             | `"down"`        | `comparison`      |
| `=`             | `"flat"`        | `comparison`      |
| `--`            | `None`          | `respondents`     |

Value strings are preserved verbatim — no PT-BR → float conversion at
the fetcher boundary. Downstream consumers (chart builder) parse the
strings on demand via `skills.ddm.focus.helpers.parse_numeric`.

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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
```

This is more comprehensive than the headers used by the `/acoes` and
`/indices` endpoints (which only set User-Agent + Accept) because
CloudFront's WAF on `/boletim-focus` enforces stricter rules.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — NEVER DO + ALWAYS DO rules.
- [`../DDM.md`](../DDM.md) — DDM domain landing page (covers all 5 sub-domains).
