# DDM Focus — INSTRUCTIONS

Rules of engagement for the DDM focus sub-domain. Read before editing.

## NEVER DO

1. **NEVER strip the PT-BR formatting from the value columns.**
   - `"5,151%"` → must be stored as `"5,151%"` (string, verbatim) in the
     `four_weeks_ago` / `one_week_ago` / `today` columns.
   - `"R$ 5,200"` → must be stored as `"R$ 5,200"` (string, verbatim).
   - The dashboard renders these strings as-is so the user sees exactly
     what the source shows. Only the chart builder parses them to floats
     (via `skills.ddm.focus.helpers.parse_numeric`).

2. **NEVER drop the comparison glyph.**
   - `▲` → must become `"up"` at the fetcher boundary
     (`_normalize_comparison`).
   - `▼` → must become `"down"`.
   - `=` → must become `"flat"`.
   - Empty / `--` / unrecognized → `""`.
   - The dashboard re-renders the glyphs (via `comparison_symbol`) and
     applies colors (green / red / gray) so the user sees the same
     visual feedback as on the source page.

3. **NEVER add BeautifulSoup / lxml as a dependency.**
   - All HTML parsing is regex-based (`re` stdlib).
   - The site is server-rendered HTML with a stable shape; a regex parser
     is sufficient and keeps the dependency surface minimal.

4. **NEVER write to `memory_db/ddm/focus.db` from a query mode.** Query
   modes (`focus_data`, `last`, `indicator`, `search`, `summary`, `status`)
   open connections with `read_only=True` (SQLite URI `mode=ro`). Writes
   happen only in `sync_engine.py`.

5. **NEVER share a single SQLite connection across threads.**
   - `sync_all` is a single HTTP call + parse + single-thread DB write —
     no `ThreadPoolExecutor` needed for focus (unlike inflation/juros/
     poupanca which fetch N pages concurrently).

6. **NEVER omit the full browser headers when fetching.**
   - The `/boletim-focus` endpoint is CloudFront-protected and rejects
     bare or identifying bot User-Agents with a 403.
   - ALWAYS use the full Chrome 127 header set defined in
     `fetcher._BROWSER_HEADERS` (User-Agent + Accept + Accept-Language +
     Accept-Encoding + Connection + Upgrade-Insecure-Requests).
   - Do NOT simplify to a single User-Agent header — the WAF rules on
     this endpoint are stricter than on `/acoes` and `/indices`.

7. **NEVER treat `--` as 0.** It is the DDM missing-value marker and
   MUST be stored as `None` in the DB. Downstream code treats `None` as
   "no data" (renders as "-").

8. **NEVER run network calls in tests.** All fetcher tests use synthetic
   HTML fixtures; all dashboard tests mock `query_engine.all_data` +
   `summary`.

9. **NEVER hardcode the year-to-table mapping.** The Boletim Focus page
   may swap the table order or add/remove intermediate `<div>` wrappers.
   The year is identified at parse time by walking backwards from each
   table to the nearest preceding `<h2>` or `<h3>` heading that contains
   a 4-digit year (see `_find_year_for_table`). Hardcoding "table 1 is
   2026, table 2 is 2027, ..." would break if DDM reorders the page.

10. **NEVER store the raw glyph (`▲` / `▼` / `=`) in the DB.** Always
    normalize via `_normalize_comparison` so downstream consumers can
    branch on the string `"up"` / `"down"` / `"flat"` without
    re-parsing Unicode.

## ALWAYS DO

1. **ALWAYS use `from __future__ import annotations` at the top of every
   `.py` file.** This is the project convention — every existing module
   follows it.

2. **ALWAYS preserve the PT-BR value strings verbatim.** The DB columns
   `four_weeks_ago` / `one_week_ago` / `today` are `TEXT` and hold only
   the original source strings. The dashboard renders them as-is.

3. **ALWAYS use `INSERT OR REPLACE` for syncs.** Re-syncing the same
   day replaces existing rows rather than appending duplicates. The
   `(year, indicator, ref_date)` primary key enforces this.

4. **ALWAYS use Portuguese for user-facing strings.** Section titles,
   KPI labels, error messages, dashboard tab names, and chart titles
   should all be in PT-BR (e.g. "Data de referencia", "Anos cobertos",
   "Indicadores", "Total de observacoes", "Ha 4 semanas", "Erro ao
   consultar"). The Comp. column glyph is rendered without a label
   (the triangle speaks for itself).

5. **ALWAYS emit a `chart_data` Chart.js config in chart sections** (not
   top-level `labels` / `values`). The `dashboard.html` template reads
   `sec.chart_data` and passes it to `new Chart(canvas, config)`.

6. **ALWAYS emit `column_align` on every table.** The `macros.html`
   `data_table` macro reads `sec.column_align` and applies
   `text-align: right` + `tabular-nums` on right-aligned columns.

7. **ALWAYS emit `sortable=True` + `default_sort` + `sort_types` on the
   year and indicator tables.** The sortable-table feature (introduced
   in ddm/acoes v1) lets users click column headers to sort asc/desc.
   - Year table: `default_sort = {"column": 0, "direction": "asc"}`
     (Indicador ASC), `sort_types = ["text","text","text","text",
     "text","number"]`.
   - Indicator table: `default_sort = {"column": 0, "direction": "asc"}`
     (Ano ASC), `sort_types = ["number","text","text","text","text",
     "number"]`.

8. **ALWAYS include a `data-value` attribute on numeric cells.** The
   JS `sortTable()` function reads `data-value` for accurate numeric
   sorting — without it, "5,151%" would be sorted as text and land in
   the wrong position. The `_value_numeric_cell` helper emits
   `{"text": "5,151%", "data-value": "5.151000"}` dicts; the macro
   reads the dict and renders `<td data-value="5.151000">5,151%</td>`.

9. **ALWAYS emit a colored comparison cell.** The Comp. column cell is
   a dict `{"text": "▲", "color": "#22c55e"}` so the macro applies the
   color override inline (green for up, red for down, gray for flat).

10. **ALWAYS promote per-tab KPIs to the top-level `kpis` array.** The
    dashboard template renders KPIs in a universal header above the tabs,
    not per-tab. The dashboard collects them via the `summary()` query
    mode (one DB call).

11. **ALWAYS handle missing data gracefully.** The dashboard returns
    `status="ok"` even when individual sub-queries fail; failed tabs get
    an error section via `build_error_section`. This mirrors the
    `cvm/financials` + `bcb/macro` + `ddm/inflation` + `ddm/juros` +
    `ddm/poupanca` + `ddm/acoes` graceful-degradation contract.

12. **ALWAYS run `py_compile` on changed files before declaring done.**
    `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

13. **ALWAYS update `INSTRUCTIONS.md` + `CHANGELOG.md` + `API.md` when
    adding a new mode, schema column, or sync behavior change.** Docs
    are part of the contract.

14. **ALWAYS pass `sort_types` to the data_table macro when emitting a
    sortable table.** The macro supports both an explicit `sort_types`
    list (preferred) and an implicit fallback that derives the sort type
    from `column_align` (right → number, left → text). For the focus
    tables the explicit list is `["text","text","text","text","text",
    "number"]` (year table) or `["number","text","text","text","text",
    "number"]` (indicator table).

15. **ALWAYS parse values to floats ONLY in the chart builder.** The
    `parse_numeric` helper in `skills.ddm.focus.helpers` strips the `R$`
    prefix, `%` suffix, dot thousands, and comma decimal to produce a
    clean float for Chart.js. Do NOT call `parse_numeric` from the table
    builders — they must preserve the original string.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
