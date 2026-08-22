# DDM Acoes Skill — Changelog

## v1.0 — 2025-01

Initial release. 1-tab dashboard with sortable stocks table + price-
distribution chart. Mirrors `ddm/poupanca` skill pattern (1 tab, KPIs at
top, no Comparativo), adapted for the flat stocks-list page.

### Added (5 files + modes/__init__.py)

- `skills/ddm/acoes/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm-acoes"]`
  (own source key — separate from `ddm` (inflation), `ddm-juros`, and
  `ddm-poupanca`).
- `skills/ddm/acoes/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/acoes/helpers.py` — `format_brl(v)` (R$ 44,30),
  `format_int(v)` (PT-BR thousands: 52.792.400), `format_pct(v)` (signed
  PT-BR percentage: +2,78% / -10,85%), `format_value(v, unit)`,
  `_format_mes_ano(ref_date)`.
- `skills/ddm/acoes/report.py` — `build_kpi_card`, `build_stocks_table`
  (sortable: `sortable=True` + `default_sort={"column": 2, "direction":
  "desc"}` + `sort_types=["text","text","number","number","number"]` +
  per-cell `{"text": ..., "data-value": ...}` dict for numeric cells +
  `negative_red=True`), `build_distribution_chart` (Chart.js bar with
  16 colored bars from `skills._price_colors.price_distribution()` —
  each bar gets its range's color so the chart is a single-glance view
  of where B3 prices cluster), `build_error_section`.
- `skills/ddm/acoes/modes/dashboard.py` — 1-tab dashboard.
- `skills/ddm/acoes/modes/__init__.py` — modes package marker.

### Dashboard: 1 tab (no subtabs, no Comparativo)

1. **Ações** (group: Ações) — 4 top-level KPIs (Total de Ações, Mais
   Negociada, Maior Alta, Maior Baixa) + sortable stocks table (5
   columns: Ticker | Nome | Negócios | Última (R$) | Variação) +
   price-distribution chart (16 colored bars, one per price-range bucket
   from `skills/_price_colors.py`).

### Section titles (no skill-name prefix)

Section titles do NOT prefix with the skill name (already in tab name)
— a deliberate v1 design choice for cleaner headers (mirrors the
`ddm/poupanca` v1 design choice):

- "Ações B3" (the stocks table — kept because it identifies the source,
  not the skill name)
- "Distribuição de Preços" (the chart)

### Sortable table feature (new in v1)

This skill introduces the sortable-table feature to the dashboard
ecosystem:

- `macros.html` `data_table` macro gains 3 new optional parameters:
  `sortable` (bool), `default_sort` (dict with `column` + `direction`),
  `sort_types` (list of "text" / "number" per column).
- `base.html` gains the `sortTable(th, colIndex)` JS function + CSS for
  `.data-table th.sortable` (cursor: pointer + arrow indicators).
- Each numeric cell carries a `data-value` attribute with the raw float
  so the JS sorter doesn't have to parse PT-BR display text.
- Default sort: **Negócios DESC** (column index 2) — mirrors the DDM
  page's pre-sort so the dashboard's initial state matches what the
  user sees on the source page.

The sortable-table feature is fully backward-compatible: when
`sortable=False` (the default), the macro emits plain `<th>` elements
without `onclick` handlers (existing tables are unaffected).

### Price-distribution chart (new in v1)

A Chart.js bar chart with 16 colored bars (one per price-range bucket
from `skills/_price_colors.py`). Each bar's color matches its range
(red → pink → yellow → green → teal → blue). The chart is a single-
glance view of where B3 prices cluster (most stocks trade below R$50).

The 16-range palette is centralized in `skills/_price_colors.py` so
future skills that display stock prices share the same visual language.

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-acoes` entry that
calls `data_sources.ddm.acoes.sync_engine.sync_all(force=True)`. The
acoes skill declares `REQUIRED_SOURCES = ["ddm-acoes"]` so the sync
guard auto-refreshes `acoes.db` before each dashboard run.

`skills/_freshness.py` (NEW top-level freshness helper) also gained a
`ddm-acoes` entry in `get_freshness()` so consumers can poll the
last-sync timestamp for any DDM sub-domain from a single dict.

### Tests

- `tests/data_sources/ddm/acoes/test_fetcher.py` — 14 tests covering
  `_parse_br_int`, `_parse_br_number`, `_parse_variation` (with sign,
  without sign, missing values), `parse_stocks_table` (page order,
  fields, negative variation, anchor-tag stripping, empty HTML,
  `normal-table` fallback, malformed-row skip).
- `tests/skills/ddm/acoes/test_dashboard.py` — 16 tests covering tab
  structure (1 tab + group="Ações"), KPI promotion (4 KPIs: Total de
  Ações + Mais Negociada + Maior Alta + Maior Baixa), sortable table
  (`sortable=True` + `default_sort` + `sort_types` + `column_align` +
  `negative_red` + 5 columns + numeric-cell dict shape + variation
  text sign), and price-distribution chart (16 bars, counts match input
  prices, bar colors match `skills._price_colors.ALL_RANGES` palette,
  chart + section titles).
