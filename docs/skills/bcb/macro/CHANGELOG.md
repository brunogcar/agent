<- Back to [MACRO](../MACRO.md)

# 📋 Macro Changelog

## v1.6 — 2026-08-27

**Sortable tables + DD/MM/YYYY dates + charts show all data + collapsible tables + monthly Juros/Retorno Real + merged Cambio + Focus dedup.**

### Tables — sortable + DD/MM/YYYY (all 8 tabs)

- **`report.build_table_section`** now accepts `sortable`, `default_sort`,
  `sort_types`, `negative_red`, `column_align`, `collapsible` params (passed
  through to the `data_table` Jinja macro). Default: `sortable=True` with
  Data DESC (newest first).
- **`helpers.build_observation_rows`** now returns date cells as dicts with
  `{text: DD/MM/YYYY, data-value: YYYY-MM-DD}` — the `data-value` attribute
  carries the ISO date so the `sortTable` JS sorts chronologically (not
  lexicographically on DD/MM/YYYY).
- **New `helpers.format_date(iso)`** — converts ISO YYYY-MM-DD to PT-BR
  DD/MM/YYYY. Also handles monthly YYYY-MM → MM/YYYY.
- All tables across all 8 tabs now have:
  - `sortable=True` + `default_sort={"column": 0, "direction": "desc"}`
  - Dates displayed as DD/MM/YYYY
  - `negative_red=True` on Retorno Real table (negative real rates in red)
  - `column_align` on all tables (left for dates/labels, right for numbers)
- Inline tables (real_returns, expectations, yield_curve) also updated.

### Collapsible tables (all tabs except Resumo)

- All table sections in Indicadores + Analise tabs now have `collapsible=True`
  (collapsed by default). Charts are visible without scrolling; tables expand
  on click.
- `build_table_section` + `build_chart_section` now accept a `collapsible` param.

### Charts — show all available data (~5 years)

- **Dashboard defaults bumped**: `days=3650` (was 365), `months=60` (was 24).
  The SGS DB has ~1264-1840 daily rows (~5 years). The old `days=365` cap
  wasted 70% of the data. The range selector lets users zoom in.
- **Atividade tab**: `days=3650` (was 730) for PIB + Salario minimo.
- **Cambio tab**: monthly USD/BRL chart now fetches `days=3650` (was 730) +
  shows `n_months=60` (was 24).

### Chart x-axis date format + range selector fix

- Added `_applyDateFormatXAxis` JS function — converts ISO YYYY-MM-DD labels
  to DD/MM/YYYY at render time (post-clone tick callback). Also handles
  YYYY-MM → MM/YYYY. Skips charts with non-date labels (e.g. year-only
  "2026" in Curva de Juros).
- Fixed range selector breaking charts on sub-Tudo ranges: `labelToISO`
  now handles ISO YYYY-MM-DD passthrough (was only DD/MM/YYYY + Mon/YYYY).

### Juros tab — monthly table (was daily)

- `rates.py` tables now show MONTHLY data (last value per month) instead of
  daily. Selic changes ~every 45 days, not daily — a daily table is mostly
  redundant. Monthly view is more meaningful.
- New `helpers.group_by_month(observations)` — groups daily obs by YYYY-MM,
  keeps the last value of each month.

### Cambio tab — merged charts + 2 collapsible tables

- Merged the 2 daily charts (BRL/USD + USD/BRL) into 1 chart showing BRL/USD
  (the common Brazilian convention — reais per dollar, ~5.x).
- Kept 2 separate collapsible tables: one for BRL/USD (5.x), one for USD/BRL
  (1/rate = ~0.19, dollars per real).
- Monthly chart + table also collapsible.

### Retorno Real tab — monthly table (was daily)

- Table now shows MONTHLY data (last value per month) instead of daily.
  Daily changes are not important for real returns — monthly view is more
  meaningful and easier to read.
- Shows last 24 months (was last 10 daily observations).

### Expectativas Focus tab — deduplicated + collapsible

- Table rows now deduplicated: when multiple survey rounds happen on the
  same day for the same reference period (same `data` + `data_referencia`),
  only the one with the MOST respondents is kept. Previously duplicate rows
  appeared with slightly different values, causing confusion.
- Chart also deduplicated (same logic).
- Tables collapsible=True.

### Curva de Juros tab — removed range selector

- Removed `price_range_selector` from the yield curve chart. This is a
  forward-looking prediction chart (years on x-axis), not historical data —
  the range selector (1M/3M/6M/1A/5A/10A) doesn't apply.
- Table collapsible=True.

### Green dot tab bug — already fixed

The green dot not switching when clicking tabs was already fixed in commit
`468b300` (CSS rule `.nav-item.active .nav-dot { background: #22c55e; }`).
The uploaded dashboard HTML was generated from an older version — regenerating
the dashboard picks up the fix.

### Tests

- 7 new tests: `test_dashboard_tables_are_sortable`,
  `test_dashboard_table_date_cells_are_dd_mm_yyyy`,
  `test_dashboard_charts_show_all_available_data`,
  `test_format_date_converts_iso_to_pt_br`,
  `test_dashboard_tables_are_collapsible`,
  `test_rates_table_is_monthly`,
  `test_yield_curve_chart_has_no_range_selector`,
  `test_group_by_month`.
- All 8 existing tests still pass (no breakage).

## v1.5 — 2026-09-05

**Yield curve mode (Focus expected Selic) — 8th 'Curva de Juros' tab. BMF DI futures deferred (no public URL).**
