# DDM Fluxo — INSTRUCTIONS

Rules of engagement for the DDM fluxo sub-domain. Read before editing.

## NEVER DO

1. **NEVER store raw PT-BR value strings in the DB.** Unlike ddm/focus
   (which preserves `"5,151%"` verbatim because the page mixes percentage,
   currency, and integer-count columns), the fluxo page has a single
   unit (millions of R$) across all 5 value columns. Parse to float at
   the fetcher boundary via `_parse_br_number`:
   - `"-1.582,35 mi"` → `-1582.35`
   - `"1.029,81 mi"` → `1029.81`
   - `"42,36 mi"` → `42.36`
   - `"--"` → `None`
   Storing as REAL enables numeric sorting, monthly/annual aggregations
   (SUM, running cumulative), and Chart.js rendering without re-parsing.

2. **NEVER store dates as DD/MM/YYYY in the DB.** Always normalize to
   ISO `YYYY-MM-DD` at the fetcher boundary via `_parse_br_date`. The DB
   column `ref_date` is `TEXT` and holds only ISO dates. The dashboard
   re-formats to DD/MM/YYYY for display via `format_date`.

3. **NEVER add BeautifulSoup / lxml as a dependency.**
   - All HTML parsing is regex-based (`re` stdlib).
   - The site is server-rendered HTML with a stable shape; a regex parser
     is sufficient and keeps the dependency surface minimal.

4. **NEVER write to `memory_db/ddm/fluxo.db` from a query mode.** Query
   modes (`fluxo_data`, `last`, `search`, `summary`, `ticker`,
   `fluxo_by_investor`, `monthly_cumulative`, `annual_cumulative`,
   `status`) open connections with `read_only=True` (SQLite URI
   `mode=ro`). Writes happen only in `sync_engine.py`.

5. **NEVER share a single SQLite connection across threads.**
   - `sync_all` is a single HTTP call + parse + single-thread DB write —
     no `ThreadPoolExecutor` needed for fluxo (unlike inflation/juros/
     poupanca which fetch N pages concurrently).

6. **NEVER omit the full browser headers when fetching.**
   - The `/fluxo` endpoint is CloudFront-protected and rejects bare or
     identifying bot User-Agents with a 403.
   - ALWAYS use the full Chrome 127 header set defined in
     `fetcher._BROWSER_HEADERS` (User-Agent + Accept + Accept-Language +
     Connection + Upgrade-Insecure-Requests).
   - Do NOT simplify to a single User-Agent header.

7. **NEVER treat `--` as 0.** It is the DDM missing-value marker and
   MUST be stored as `None` in the DB. Downstream code treats `None` as
   "no data" (renders as "-", excluded from sums).

8. **NEVER run network calls in tests.** All fetcher tests use synthetic
   HTML fixtures; all dashboard tests mock `query_engine.fluxo_data` +
   `summary` + `monthly_cumulative` + `annual_cumulative`.

9. **NEVER confuse the "ticker" mode parameter with a stock ticker.** In
   this sub-domain the `ticker` slot is a date (the dashboard uses dates
   as the primary key, not stock tickers). The mode name is kept for
   API parity with the other DDM sub-domains (acoes / inflation / juros
   / poupanca / focus all have a `ticker` mode).

10. **NEVER sort observations DESC when the dashboard expects ASC.** The
    `/fluxo` page is DESC (newest first), but the dashboard's chart
    builders sort ASC internally so time flows left-to-right. The table
    builders leave the order as-is and rely on the table's
    `default_sort = {"column": 0, "direction": "desc"}` to display
    newest-first.

## ALWAYS DO

1. **ALWAYS use `from __future__ import annotations` at the top of every
   `.py` file.** This is the project convention — every existing module
   follows it.

2. **ALWAYS parse values to floats at the fetcher boundary.** The DB
   columns `estrangeiro` / `institucional` / `pessoa_fisica` /
   `inst_financeira` / `outros` are `REAL`. Use `_parse_br_number` which
   handles the PT-BR format (dot thousands, comma decimal, "mi" suffix).

3. **ALWAYS parse dates to ISO YYYY-MM-DD at the fetcher boundary.** Use
   `_parse_br_date`. The dashboard re-formats to DD/MM/YYYY for display
   via `format_date` (in `skills/ddm/fluxo/helpers.py`).

4. **ALWAYS use `INSERT OR REPLACE` for syncs.** Re-syncing the same
   day replaces existing rows rather than appending duplicates. The
   `ref_date` primary key enforces this.

5. **ALWAYS use Portuguese for user-facing strings.** Section titles,
   KPI labels, error messages, dashboard tab names, and chart titles
   should all be in PT-BR (e.g. "Ultima data", "Total Estrangeiro",
   "Fluxo diario por investidor", "Acumulado mensal", "Erro ao
   consultar").

6. **ALWAYS emit a `chart_data` Chart.js config in chart sections** (not
   top-level `labels` / `values`). The `dashboard.html` template reads
   `sec.chart_data` and passes it to `new Chart(canvas, config)`.

7. **ALWAYS emit `column_align` on every table.** The `macros.html`
   `data_table` macro reads `sec.column_align` and applies
   `text-align: right` + `tabular-nums` on right-aligned columns.

8. **ALWAYS emit `sortable=True` + `default_sort` + `sort_types` on the
   fluxo tables.** The sortable-table feature (introduced in ddm/acoes
   v1) lets users click column headers to sort asc/desc.
   - Fluxo table: `default_sort = {"column": 0, "direction": "desc"}`
     (Data DESC = newest first), `sort_types = ["text","number","number",
     "number","number","number"]`.
   - Investor table: `default_sort = {"column": 0, "direction": "desc"}`,
     `sort_types = ["text","number"]`.

9. **ALWAYS include a `data-value` attribute on numeric cells.** The
   JS `sortTable()` function reads `data-value` for accurate numeric
   sorting — without it, "-1.582,35 mi" would be sorted as text.
   - Date cells: `data-value = "2026-08-19"` (ISO date, so chronological
     sort works).
   - Value cells: `data-value = "-1582.350000"` (raw float, so numeric
     sort works).

10. **ALWAYS emit `negative_red=True` on the fluxo + investor tables.**
    Outflows (negative values) render in red, making it visually obvious
    which days / investors had net selling.

11. **ALWAYS promote per-tab KPIs to the top-level `kpis` array.** The
    dashboard template renders KPIs in a universal header above the tabs,
    not per-tab. The dashboard collects them via the `summary()` query
    mode + in-memory sum per investor.

12. **ALWAYS handle missing data gracefully.** The dashboard returns
    `status="ok"` even when individual sub-queries fail; failed tabs get
    an error section via `build_error_section`. This mirrors the
    `cvm/financials` + `bcb/macro` + `ddm/inflation` + `ddm/juros` +
    `ddm/poupanca` + `ddm/acoes` + `ddm/focus` graceful-degradation
    contract.

13. **ALWAYS run `py_compile` on changed files before declaring done.**
    `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

14. **ALWAYS update `INSTRUCTIONS.md` + `CHANGELOG.md` + `API.md` when
    adding a new mode, schema column, or sync behavior change.** Docs
    are part of the contract.

15. **ALWAYS emit the 3 range-selector keys together** (`price_range_selector`
    + `price_full_labels` + `price_full_datasets`) on charts that opt
    into the range selector. The template's `filterPriceChart` JS
    requires all 3 — missing any one silently breaks the buttons.

16. **ALWAYS use `_normalize_investor` in the query engine before
    interpolating a column name into SQL.** The helper maps both the
    canonical column name (`"estrangeiro"`) and the PT-BR display label
    (`"Pessoa física"` → `pessoa_fisica`) to the safe DB column name.
    Never interpolate raw user input into a SQL string.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
