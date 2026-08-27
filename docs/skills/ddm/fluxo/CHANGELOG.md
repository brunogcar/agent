# DDM Fluxo Skill — Changelog

## v1.1 — 2026-08-27

### Dashboard KPI + table improvements

**KPI boxes — 2 rows of 5 (10 total):**
- **Row 1 (YTD):** `Ultima data` (DD/MM/YYYY) + 4 `Liquido anual {investor}` —
  year-to-date net per investor (sum of daily values where `ref_date` starts
  with the current year). Values auto-scale: ≥1B reais → `bi`, <1B → `mi`.
  Replaces the old 4 `Total {investor}` KPIs that showed since-inception totals.
- **Row 2 (Rolling 365 days):** `Dias na base` (total day count in DB) + 4
  `Liquido 365d {investor}` — last 365 days net per investor (sum of daily
  values where `ref_date >= last_date - 365 days`).

**Number formatting — `format_brl_from_millions()` (new helper):**
- Added `skills/ddm/fluxo/helpers.py:format_brl_from_millions(value)` — wraps
  `core/br_validator.py:format_brl()` with a millions→units conversion
  (×1_000_000) and EN→PT-BR suffix mapping (`B`→`bi`, `M`→`mi`, `T`→`tri`).
- Also moves the negative sign from before `R$` to after (br_validator produces
  `-R$ 3,86 B`, we produce `R$ -3,86 bi` to match the existing `format_brl`
  convention used in table cells).
- Examples: `20017.83` → `"R$ 20,02 bi"`, `44.94` → `"R$ 44,94 mi"`,
  `-39972.79` → `"R$ -39,97 bi"`.
- Table cells keep `format_brl()` (full precision in millions) for row-by-row
  comparison; KPI cards use `format_brl_from_millions()` for readability.

**Table sorting — DESC by date (newest first):**
- `build_fluxo_table()` + `build_investor_table()` in `report.py` now sort
  observations DESC by `ref_date` BEFORE building rows. Previously rows were
  emitted in ASC order (oldest first) while the header showed a `sort-desc`
  arrow — the JS sorter only fires on click, not on page load, causing a
  visual mismatch.
- Applies to all 13 tables in the dashboard:
  - Tab 1 Fluxo: 1 daily table
  - Tabs 2–5: 3 subtabs each (Diario, Mensal, Anual) = 12 investor tables
- The Mensal subtab now passes `date_label` (`"Ago/2026"`) for display while
  keeping `ref_date` (`"2026-08"`) for sorting — previously showed `"2026-08"`
  raw in the Data column.

## v1.0 — 2025-01

Initial release. 5-tab dashboard with multi-subtab structure per tab.

### Added (5 files + modes/__init__.py)

- `skills/ddm/fluxo/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm-fluxo"]`
  (own source key — separate from `ddm` (inflation), `ddm-juros`,
  `ddm-poupanca`, `ddm-acoes`, and `ddm-focus`).
- `skills/ddm/fluxo/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/fluxo/helpers.py` — `format_brl(v, unit="mi")` (PT-BR
  with "mi" suffix, dot thousands, comma decimal, "R$" prefix),
  `format_int(v)` (PT-BR thousands), `format_pct(v)`, `format_date(d)`
  (YYYY-MM-DD → DD/MM/YYYY for display), `format_value(v, unit)`
  (dispatch on unit).
- `skills/ddm/fluxo/report.py` — `build_kpi_card`,
  `build_fluxo_table` (sortable: `sortable=True` + `default_sort=
  {"column": 0, "direction": "desc"}` (Data DESC = newest first) +
  `sort_types=["text","number","number","number","number","number"]` +
  per-cell `{"text": ..., "data-value": ...}` dict for numeric cells +
  `{"text": "19/08/2026", "data-value": "2026-08-19"}` for date cells +
  `negative_red=True`), `build_fluxo_chart` (Chart.js bar with 4
  datasets: Estrangeiro blue, Institucional red, Pessoa física amber,
  Inst. Financeira green; X-axis = dates DD/MM/YYYY; range selector),
  `build_investor_daily_chart` (single dataset + per-bar green/red
  backgroundColor array + range selector), `build_investor_monthly_chart`
  (line chart + per-point green/red point colors), `build_investor_annual_chart`
  (line chart green + range selector), `build_investor_table` (2-column
  sortable + `negative_red=True`), `build_error_section`.
- `skills/ddm/fluxo/modes/dashboard.py` — 5-tab dashboard.
- `skills/ddm/fluxo/modes/__init__.py` — modes package marker.

### Dashboard: 5 tabs

1. **Fluxo** (group: Fluxo) — bar chart with 4 investor datasets +
   sortable table of all daily observations. Top-level KPIs are
   promoted from `summary()` + in-memory sum per investor.

2-5. **Per investor** (group: Investidores) — One tab per investor
   (Estrangeiro, Institucional, Pessoa física, Inst. Financeira).
   Each tab has 3 subtabs:
   - **Diário** — daily bar chart (single dataset, per-bar green/red
     colors) + sortable daily table (Data | Valor (mi)).
   - **Mensal** — monthly cumulative line chart (sum of daily values
     per month, green for positive months, red for negative) +
     sortable monthly table.
   - **Anual** — running annual cumulative line chart (each day =
     previous + today) + sortable cumulative table.

### Section titles (no skill-name prefix)

Section titles do NOT prefix with the skill name (already in tab name)
— a deliberate v1 design choice for cleaner headers (mirrors the
`ddm/focus` convention):

- "Fluxo diario por investidor" (Fluxo tab chart)
- "Tabela diaria completa" (Fluxo tab table)
- "Fluxo diario - Estrangeiro" (Estrangeiro Diario chart)
- "Acumulado mensal - Institucional" (Institucional Mensal chart)
- "Acumulado anual - Pessoa fisica" (Pessoa física Anual chart)

### Sync wiring

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm-fluxo` entry
that calls `data_sources.ddm.fluxo.sync_engine.sync_all(force=True)`.
The fluxo skill declares `REQUIRED_SOURCES = ["ddm-fluxo"]` so the
sync guard auto-refreshes `fluxo.db` before each dashboard run.

`skills/_freshness.py` also gained a `ddm-fluxo` entry in
`get_freshness()` so consumers can poll the last-sync timestamp for
any DDM sub-domain from a single dict (now 6 keys: `ddm`, `ddm-juros`,
`ddm-poupanca`, `ddm-acoes`, `ddm-focus`, `ddm-fluxo`).

### Tests

- `tests/data_sources/ddm/fluxo/test_fetcher.py` — 17 tests covering
  `_parse_br_number`, `_parse_br_date`, `_strip_html`,
  `parse_fluxo_table` (rows per table, ref_date ISO, value parsing to
  floats, negatives in all columns, empty HTML, malformed-row skip,
  header-row skip, no-class fallback, source-order preservation).
- `tests/skills/ddm/fluxo/test_dashboard.py` — 30 tests covering tab
  structure (5 tabs: 1 Fluxo + 4 investors), tab groups (Fluxo /
  Investidores), Fluxo tab chart + table, investor tab 3 subtabs +
  per-subtab chart + table, KPI promotion (5 top-level KPIs: 1 date +
  4 investor totals), Fluxo table sortable features, investor table
  sortable features, chart structure (4 datasets in Fluxo chart +
  dataset labels + dataset colors + bar type + range selector, 1
  dataset in daily chart + per-bar green/red colors + range selector,
  line chart in monthly + annual, range selector in annual).
