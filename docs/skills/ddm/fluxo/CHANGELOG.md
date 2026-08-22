# DDM Fluxo Skill — Changelog

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

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-fluxo` entry
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
