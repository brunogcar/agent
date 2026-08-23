# DDM Juros Skill — Changelog

## v1.0 — 2025-01

Initial release. Mirrors `ddm/inflation` skill pattern, adapted for the
matrix-only juros pages with subtabs + 3-dataset charts.

### Added (5 files)

- `skills/ddm/juros/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm"]`.
- `skills/ddm/juros/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/juros/helpers.py` — `format_value`, `format_pct`,
  `compute_stats`, `_format_mes_ano` (ref_date → Portuguese Mês/Ano),
  `_heat_color` (red→white→green diverging color), `build_observation_rows`
  (4-column rows: Mês/Ano | Índice do mês | Média no ano | Média 12m).
- `skills/ddm/juros/report.py` — `build_kpi_card`, `build_chart_section`
  (3 datasets: month_value + media_no_ano + media_12m, NOT 2 like
  inflation), `build_overlay_chart_section` (multi-index overlay for
  Comparativo tab), `build_table_section` (4 columns, with
  `column_align` + `descending` flag for DESC display),
  `build_matrix_table_section` (heatmap with red→white→green diverging
  for all 12 month columns - NO "Ano" column, carries `cell_colors` +
  `heatmap` metadata), `build_text_section`, `build_error_section`.
- `skills/ddm/juros/modes/dashboard.py` — 4-tab dashboard with subtabs.

### Dashboard: 4 tabs (with subtabs)

1. **Selic** (group: Indices) — subtabs: Histórico + Matriz.
2. **Meta Selic** (group: Indices) — same shape.
3. **CDI** (group: Indices) — same shape.
4. **Comparativo** (group: Analise) — overlay chart (month_value for all
   3 indices, last 24 months), NO tables.

Each per-index tab is ONE `type:"subtabs"` section with 2 subtabs:

- **Histórico**: 3 KPIs (month_value, media_no_ano, media_12m) +
  3-dataset line chart + history table (DESC).
- **Matriz**: monthly matrix table (year × Jan..Dez, NO "Ano" column)
  with diverging red→white→green heatmap coloring on all 12 columns.

### Chart colors

| Index      | Color  | Hex       | Secondary (media_no_ano) | Hex       |
| ---------- | ------ | --------- | ------------------------ | --------- |
| Selic      | teal   | `#0d9488` | teal-300                 | `#5eead4` |
| Meta Selic | blue   | `#3b82f6` | blue-300                 | `#93c5fd` |
| CDI        | amber  | `#f59e0b` | amber-300                | `#fcd34d` |

### Differences from `ddm/inflation` v1.0

| Aspect                       | `inflation` v1.0                | `juros` v1.0                                   |
| ---------------------------- | ------------------------------- | ---------------------------------------------- |
| Tab structure                | Flat (3 sections per tab)       | Subtabs (Histórico + Matriz)                   |
| Chart datasets               | 2 (month_value + acumulado_12m) | 3 (month_value + media_no_ano + media_12m)     |
| Matrix "Ano" column          | Yes (sequential blue color)     | No (all 12 months use diverging red→green)     |
| Matrix heatmap               | No (plain text)                 | Yes (red→white→green on all 12 columns)        |
| KPI labels                   | "(mes)", "(ano)", "(12m)"       | "(mes)", "(media ano)", "(media 12m)"          |
| Table columns                | 4 (Variation + Acumulado)       | 4 (Indice + Média no ano + Média 12m)          |

### Sync wiring

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm-juros` entry that
calls `data_sources.ddm.juros.sync_engine.sync_all(force=True)`. The
juros skill declares `REQUIRED_SOURCES = ["ddm"]` (auto-refreshes
inflation.db before dashboard run; the `ddm-juros` entry is available
for explicit invocation via `_trigger_sync("ddm-juros")`).

### Tests

- `tests/data_sources/ddm/juros/test_fetcher.py` — 12 tests covering
  `_parse_br_number`, `_parse_data_value`, `parse_matrix_only` (years,
  month header with NO "Ano", data values, empty HTML, stray "Ano"
  filter), and `flatten_matrix_to_observations` (sorting, missing-cell
  skip, month_value, media_no_ano, media_12m full + short window +
  year-boundary cross).
- `tests/skills/ddm/juros/test_dashboard.py` — 11 tests covering tab
  structure (4 tabs), subtabs structure (Histórico + Matriz), KPI
  promotion, 3-dataset chart, 4-column table, NO "Ano" column in matrix,
  heatmap metadata, Comparativo chart-only, Chart.js config emission,
  PT-BR formatting, overlay dataset count.
