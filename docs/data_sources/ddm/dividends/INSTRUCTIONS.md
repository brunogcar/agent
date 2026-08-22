# DDM Dividends — INSTRUCTIONS

Rules of engagement for the DDM dividends sub-domain. Read before editing.

## NEVER DO

1. **NEVER store raw DDM strings in the DB.**
   - `"0,017250"` (comma decimal) → must become `0.017250` at the fetcher
     boundary (`_parse_br_number`).
   - `"01/07/2026"` (DD/MM/YYYY) → must become `"2026-07-01"` (YYYY-MM-DD)
     at the fetcher boundary (`_parse_br_date`).
   - `<a href="/acoes/bbdc3">BBDC3</a>` → must become `"BBDC3"` at the
     fetcher boundary (`_extract_ticker`).
   - The DB only ever holds `TEXT` ticker/tipo/date strings + `REAL` value
     floats.

2. **NEVER add BeautifulSoup / lxml as a dependency.**
   - All HTML parsing is regex-based (`re` stdlib).
   - The site is server-rendered HTML with a stable shape; a regex parser
     is sufficient and keeps the dependency surface minimal.

3. **NEVER write to `memory_db/ddm/dividends.db` from a query mode.** Query
   modes (`dividends`, `last`, `search`, `ticker`, `summary`, `status`)
   open connections with `read_only=True` (SQLite URI `mode=ro`). Writes
   happen only in `sync_engine.py`.

4. **NEVER share a single SQLite connection across threads.** The
   dividends sync is single-threaded (1 page = 1 HTTP call) so this is
   trivially satisfied, but if you parallelize, open a new connection
   per write phase.

5. **NEVER interpolate user input into SQL strings without whitelist
   validation.** `dividends_list(order_by, direction)` validates both
   against the `SORT_KEYS` whitelist before string-interpolating into
   the `ORDER BY` clause. This is the only safe way to do dynamic sort
   columns in SQLite (parameterized queries don't support column names).

6. **NEVER apply price-color logic to the Valor column.** These are
   dividend amounts (always >= 0), not stock prices. The report builder
   explicitly omits `negative_red`, `price_colors`, and `cell_colors`
   from the dividends table section. Do not re-introduce them.

7. **NEVER display dates as YYYY-MM-DD in the dashboard.** The DB stores
   them as ISO for sortability + correctness, but the dashboard displays
   PT-BR `DD/MM/YYYY` (via `helpers.format_date`). Tests assert this
   contract.

8. **NEVER run network calls in tests.** All fetcher tests use synthetic
   HTML fixtures; all dashboard tests mock `query_engine.dividends_list`
   + `summary`.

9. **NEVER drop the `(ticker, record_date, tipo)` composite primary key.**
   A company can have multiple dividends on the same record_date with
   different tipos (Dividendo + JCP), so the 3-column key is required
   for deduplication. Re-syncing replaces via `INSERT OR REPLACE`.

10. **NEVER forget the `<a>` tag fallback in `_extract_ticker`.** Most
    ticker cells wrap the code in `<strong><a href="...">TICKER</a></strong>`,
    but a few pages use `<strong>TICKER</strong>` without the anchor.
    The fallback to stripped HTML handles both shapes.

## ALWAYS DO

1. **ALWAYS use `from __future__ import annotations` at the top of every
   `.py` file.** This is the project convention — every existing module
   follows it.

2. **ALWAYS normalize raw DDM strings at the fetcher boundary.** The DB
   column types are `TEXT` (ticker, tipo, dates) + `REAL` (value), with
   dates in ISO `YYYY-MM-DD` format. Downstream code (query engine,
   dashboard, tests) assumes this.

3. **ALWAYS use `INSERT OR REPLACE` for syncs.** Re-syncing the page
   replaces existing rows rather than appending duplicates. The
   `(ticker, record_date, tipo)` primary key enforces this.

4. **ALWAYS use Portuguese for user-facing strings.** Section titles,
   KPI labels, error messages, dashboard tab names should all be in
   PT-BR (e.g. "Dividendos", "Valor total", "Maior dividendo", "Erro ao
   consultar", "Proximo pagamento").

5. **ALWAYS emit a `chart_data` Chart.js config in chart sections** (not
   top-level `labels` / `values`). The `dashboard.html` template reads
   `sec.chart_data` and passes it to `new Chart(canvas, config)`.

6. **ALWAYS emit `column_align` on tables that include numeric columns.**
   The `macros.html` `data_table` macro reads `sec.column_align` and
   applies `text-align: right` + `tabular-nums` on right-aligned columns.

7. **ALWAYS promote per-tab KPIs to the top-level `kpis` array.** The
   dashboard template renders KPIs in a universal header above the tabs,
   not per-tab. The helper uses a private `_kpis` key that the dashboard
   `pop()`s before appending the tab.

8. **ALWAYS handle missing data gracefully.** The dashboard returns
   `status="ok"` even when individual sub-queries fail; failed tabs get
   an error section via `build_error_section`. This mirrors the
   `cvm/financials` + `bcb/macro` + `ddm/inflation/juros/poupanca`
   graceful-degradation contract.

9. **ALWAYS set `sortable=True` + `sort_types` + `default_sort` on the
   dividends table.** The sortable-table feature is shipped in the
   acoes commit (macros.html + base.html + dashboard.html). The report
   builder emits these fields; the macro + JS handle the rest.

10. **ALWAYS emit Valor cells as `{"text": "R$ 0,017250", "data_value":
    "0.017250"}` dicts** (NOT plain strings). The sortable-table macro
    reads `cell.data_value` to emit `<td data-value="0.017250">R$ 0,017250</td>`,
    which the `sortTable()` JS uses for accurate numeric sorting.

11. **ALWAYS run `py_compile` on changed files before declaring done.**
    `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

12. **ALWAYS update `INSTRUCTIONS.md` + `CHANGELOG.md` + `API.md` when
    adding a new mode, column, or schema change.** Docs are part of the
    contract.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + parse pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
