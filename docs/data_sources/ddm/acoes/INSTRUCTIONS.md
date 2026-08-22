# DDM Acoes — INSTRUCTIONS

Rules of engagement for the DDM acoes sub-domain. Read before editing.

## NEVER DO

1. **NEVER store raw DDM strings in the DB.**
   - `"52.792.400"` → must become `52792400` at the fetcher boundary
     (`_parse_br_int`).
   - `"44,30"` → must become `44.30` at the fetcher boundary
     (`_parse_br_number`).
   - `"+2,78%"` / `"-10,85%"` → must become `2.78` / `-10.85` at the
     fetcher boundary (`_parse_variation`).
   - `"<a href=\"/acoes/petr4\">PETR4</a>"` → must become `PETR4` at the
     fetcher boundary (`_strip_html`).
   - `"--"` → must become `None` at the fetcher boundary.
   - The DB only ever holds normalized numbers + plain strings.

2. **NEVER add BeautifulSoup / lxml as a dependency.**
   - All HTML parsing is regex-based (`re` stdlib).
   - The site is server-rendered HTML with a stable shape; a regex parser
     is sufficient and keeps the dependency surface minimal.

3. **NEVER write to `memory_db/ddm/acoes.db` from a query mode.** Query
   modes (`stocks`, `last`, `ticker`, `search`, `summary`, `status`) open
   connections with `read_only=True` (SQLite URI `mode=ro`). Writes happen
   only in `sync_engine.py`.

4. **NEVER share a single SQLite connection across threads.**
   - `sync_all` is a single HTTP call + parse + single-thread DB write —
     no `ThreadPoolExecutor` needed for acoes (unlike inflation/juros/
     poupanca which fetch N pages concurrently).

5. **NEVER remove the `_strip_html` call on the ticker cell.** DDM wraps
   the ticker in an `<a href="/acoes/{slug}">{TICKER}</a>` element — the
   raw `<td>` HTML contains the anchor tag. The parser must extract just
   the ticker text via `_strip_html(cells[0])`.

6. **NEVER treat `--` as 0.** It is the DDM missing-value marker and
   MUST be stored as `None` in the DB. Downstream code (query engine,
   dashboard, tests) treats `None` as "no data" (renders as "-").
   Storing `0` would corrupt the price-distribution chart (would bucket
   as `X < 1`) and the "biggest gainer/loser" KPIs (would compete with
   real 0.00% variations).

7. **NEVER run network calls in tests.** All fetcher tests use synthetic
   HTML fixtures; all dashboard tests mock `query_engine.stocks_list` +
   `summary`.

8. **NEVER omit the sign on the variation field.** DDM renders variation
   with an explicit sign (`+2,78%` / `-10,85%`) — the `variation` float
   in the DB preserves that sign (positive for gains, negative for
   losses). The dashboard's `format_pct` helper re-adds the sign in the
   display string for consistency.

9. **NEVER add a "data do pregao" column to the DB.** DDM does not expose
   it on the acoes page (it's an aggregate snapshot, not a per-trade
   ledger). Use `ref_date` (scrape date, `YYYY-MM-DD`) as the proxy. If
   you need per-trade timestamps, use `data_sources/b3/cotahist/`
   (the official B3 COTAHIST file).

10. **NEVER sort by `ticker` ASC as the default dashboard state.** The
    DDM page is pre-sorted by `Negocios DESC` (most-traded first), so
    the dashboard's default sort is `Negocios DESC` to mirror what the
    user sees on the source page. Users can re-sort by clicking column
    headers (the sortable-table feature).

## ALWAYS DO

1. **ALWAYS use `from __future__ import annotations` at the top of every
   `.py` file.** This is the project convention — every existing module
   follows it.

2. **ALWAYS normalize all raw DDM strings at the fetcher boundary.** The
   DB column types are `TEXT` / `INTEGER` / `REAL` and hold only the
   normalized forms (never raw PT-BR strings).

3. **ALWAYS use `INSERT OR REPLACE` for syncs.** Re-syncing the page
   replaces existing rows rather than appending duplicates. The `ticker`
   primary key enforces this.

4. **ALWAYS use Portuguese for user-facing strings.** Section titles,
   KPI labels, error messages, dashboard tab names, and chart titles
   should all be in PT-BR (e.g. "Total de Acoes", "Mais Negociada",
   "Maior Alta", "Maior Baixa", "Distribuicao de Precos", "Acoes B3",
   "Erro ao consultar"). Note: the tab name "Acoes" does NOT repeat in
   section titles ("Acoes B3" is OK because it identifies the source,
   not the skill).

5. **ALWAYS emit a `chart_data` Chart.js config in chart sections** (not
   top-level `labels` / `values`). The `dashboard.html` template reads
   `sec.chart_data` and passes it to `new Chart(canvas, config)`.

6. **ALWAYS emit `column_align` on the stocks table.** The `macros.html`
   `data_table` macro reads `sec.column_align` and applies
   `text-align: right` + `tabular-nums` on right-aligned columns (Negocios,
   Ultima, Variacao) — without this, numeric columns would be left-
   aligned and look messy.

7. **ALWAYS emit `negative_red=True` on the stocks table.** Negative
   variations (losses) render in red so users can spot them at a glance.
   The `data_table` macro checks `cell.text.startswith('-')` and applies
   `color: #ef4444; font-weight: 600` to those cells.

8. **ALWAYS promote per-tab KPIs to the top-level `kpis` array.** The
   dashboard template renders KPIs in a universal header above the tabs,
   not per-tab. The helper uses a private `_kpis` key that the dashboard
   `pop()`s before appending the tab.

9. **ALWAYS handle missing data gracefully.** The dashboard returns
   `status="ok"` even when individual sub-queries fail; failed tabs get
   an error section via `build_error_section`. This mirrors the
   `cvm/financials` + `bcb/macro` + `ddm/inflation` + `ddm/juros` +
   `ddm/poupanca` graceful-degradation contract.

10. **ALWAYS emit `sortable=True` + `default_sort` + `sort_types` on the
    stocks table.** The sortable-table feature is the headline v1 feature
    of this skill — without `sortable=True`, the macros.html `data_table`
    macro emits plain `<th>` elements without `onclick` handlers.

11. **ALWAYS run `py_compile` on changed files before declaring done.**
    `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

12. **ALWAYS update `INSTRUCTIONS.md` + `CHANGELOG.md` + `API.md` when
    adding a new mode, schema column, or sync behavior change.** Docs
    are part of the contract.

13. **ALWAYS include a `data-value` attribute on numeric cells.** The
    JS `sortTable()` function reads `data-value` for accurate numeric
    sorting — without it, "R$ 1.234,56" would be sorted as text and
    land in the wrong position. The `build_stocks_table` helper emits
    `{"text": "R$ 44,30", "data-value": "44.300000"}` dicts; the macro
    reads the dict and renders `<td data-value="44.300000">R$ 44,30</td>`.

14. **ALWAYS use the price-distribution palette from `skills/_price_colors`
    for any new price-range visualization.** The 16-range palette is
    centralized there so changes apply across all skills. Do NOT hardcode
    color hex values in the dashboard — import `price_distribution` /
    `price_range_color` from `skills._price_colors`.

15. **ALWAYS pass `sort_types` to the data_table macro when emitting a
    sortable table.** The macro supports both an explicit `sort_types`
    list (preferred) and an implicit fallback that derives the sort type
    from `column_align` (right → number, left → text). For the stocks
    table the explicit list is `["text", "text", "number", "number",
    "number"]` (Ticker + Nome are text; Negocios + Ultima + Variacao
    are numeric).

## See also

- [`API.md`](API.md) — 8-mode reference.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file map + DB schema + pipeline.
- [`CHANGELOG.md`](CHANGELOG.md) — version history.
