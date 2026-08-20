# DDM Juros — INSTRUCTIONS

Rules of engagement for the DDM juros sub-domain. Read before editing.

## NEVER DO

1. **NEVER store raw DDM strings in the DB.**
   - `"Jul"` (matrix cell label) → must become part of the `YYYY-MM`
     `ref_date` at the derive boundary (`flatten_matrix_to_observations`).
   - `"13,15"` → must become `13.15` at the fetcher boundary
     (`_parse_br_number`).
   - `"--"` → must become `None` at the fetcher boundary.
   - The DB only ever holds `YYYY-MM` strings and `REAL` floats.

2. **NEVER add BeautifulSoup / lxml as a dependency.**
   - All HTML parsing is regex-based (`re` stdlib).
   - The site is server-rendered HTML with a stable shape; a regex parser
     is sufficient and keeps the dependency surface minimal.

3. **NEVER write to `memory_db/ddm/juros.db` from a query mode.** Query
   modes (`series`, `last`, `matrix`, `search`, `summary`, `status`) open
   connections with `read_only=True` (SQLite URI `mode=ro`). Writes happen
   only in `sync_engine.py`.

4. **NEVER share a single SQLite connection across threads.**
   - `sync_all` fetches + parses + derives concurrently in a
     `ThreadPoolExecutor` but opens one connection AFTER all threads have
     joined, for the sequential write phase.

5. **NEVER remove the `data-value` attribute fallback in
   `_parse_data_value`.** Some cells legitimately have `--` in
   `data-value`; the fallback to cell-text parsing handles edge cases
   where DDM omits the attribute.

6. **NEVER add a new index to `JUROS_CATALOG` without also adding it to the
   `skills/ddm/juros/modes/dashboard.py._INDEX_SLUGS` list.** The
   dashboard iterates over `_INDEX_SLUGS`, not the catalog, so a new index
   would be silently invisible in the dashboard.

7. **NEVER store the monthly matrix in the DB.** The matrix is parsed
   on demand via `monthly_matrix(slug)` — the 5-min fetcher cache makes
   this cheap. Only the derived historical series is stored.

8. **NEVER assume the juros matrix has an "Ano" column.** Juros pages
   ship 12 month columns only (Jan..Dez). Do NOT write code that reads
   `matrix[year]["Ano"]` — it will be `None` for every year. If you need
   a year-level aggregate, compute it from the 12 monthly cells.

9. **NEVER run network calls in tests.** All fetcher tests use synthetic
   HTML fixtures; all dashboard tests mock `query_engine.juros_history` /
   `last_value` / `monthly_matrix`.

10. **NEVER duplicate the inflation `parse_historical_table` for juros.**
    The juros pages do NOT have a historical table; the historical series
    is DERIVED from the matrix via `flatten_matrix_to_observations`. Do
    not introduce a historical-table parser for juros.

## ALWAYS DO

1. **ALWAYS use `from __future__ import annotations` at the top of every
   `.py` file.** This is the project convention — every existing module
   follows it.

2. **ALWAYS normalize matrix cells to `YYYY-MM` `ref_date` at the derive
   boundary.** The DB column is `ref_date TEXT` with `YYYY-MM` format.
   Downstream code (query engine, dashboard, tests) assumes this.

3. **ALWAYS use `INSERT OR REPLACE` for syncs.** Re-syncing an index
   replaces existing rows rather than appending duplicates. The
   `(slug, ref_date)` primary key enforces this.

4. **ALWAYS use Portuguese for user-facing strings.** Section titles,
   KPI labels, error messages, dashboard tab names, and subtab names
   should all be in PT-BR (e.g. "Indice do mes (%)", "Media 12 meses",
   "Erro ao consultar", "Historico", "Matriz").

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
   `cvm/financials` + `bcb/macro` + `ddm/inflation` graceful-degradation
   contract.

9. **ALWAYS use subtabs (`type:"subtabs"`) for the per-index tabs.** Each
   per-index tab has 2 subtabs (Historico + Matriz) wrapped in ONE
   `type:"subtabs"` section. The dashboard template renders subtabs as
   nested tabs inside the parent tab.

10. **ALWAYS run `py_compile` on changed files before declaring done.**
    `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

11. **ALWAYS update `INSTRUCTIONS.md` + `CHANGELOG.md` + `API.md` when
    adding a new mode, index, or schema change.** Docs are part of the
    contract.

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + derive pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
