# DDM Poupanca Skill — Changelog

## v1.0 — 2025-01

Initial release. Mirrors `ddm/juros` skill pattern, adapted for the
1-index poupanca subdomain (SUM-derived acumulados, NO Comparativo tab).

### Added (5 files + modes/__init__.py)

- `skills/ddm/poupanca/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm"]`.
- `skills/ddm/poupanca/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/poupanca/helpers.py` — `format_value`, `format_pct`,
  `compute_stats`, `_format_mes_ano` (ref_date → Portuguese Mês/Ano),
  `_heat_color` (**returns a dict** `{text, bg, color}` — NOT a string;
  this is the v4 fix from juros that poupanca inherits from day one),
  `build_observation_rows` (4-column rows: Mês/Ano | Rendimento |
  Acumulado no ano | Acumulado 12m).
- `skills/ddm/poupanca/report.py` — `build_kpi_card`, `build_chart_section`
  (3 datasets: month_value + acumulado_no_ano + acumulado_12m, NOT 2
  like inflation), `build_table_section` (4 columns with `column_align` +
  `descending` flag for DESC display + **`negative_red=True`** — poupanca
  yields can be negative during high-inflation periods),
  `build_matrix_table_section` (**returns `type:"heatmap"`** with
  `{text, bg, color}` cell dicts — NOT `type:"table"` and NOT a string;
  this is the v4 fix from juros that poupanca inherits from day one;
  NO "Ano" column, diverging red→white→green on all 12 month columns),
  `build_text_section`, `build_error_section`.
  **NO** `build_overlay_chart_section` (no Comparativo tab — only 1 index).
- `skills/ddm/poupanca/modes/dashboard.py` — 1-tab dashboard with subtabs.
- `skills/ddm/poupanca/modes/__init__.py` — modes package marker.

### Dashboard: 1 tab (with subtabs, NO Comparativo)

1. **Poupanca** (group: Renda Fixa) — subtabs: Histórico + Matriz.

The tab is ONE `type:"subtabs"` section with 2 subtabs:

- **Histórico**: 3 KPIs (month_value, acumulado_no_ano, acumulado_12m) +
  3-dataset line chart (emerald green solid line for month_value +
  emerald-300 dashed line for acumulado_no_ano + slate-400 dashed line
  for acumulado_12m) + history table (DESC, `negative_red=True`).
- **Matriz**: monthly matrix table (year × Jan..Dez, NO "Ano" column)
  with diverging red→white→green heatmap coloring on all 12 columns.
  Each cell is a `{text, bg, color}` dict (NOT a string).

### Section titles (no index-name prefix)

Section titles do NOT prefix with the index name (already in the tab
name) — a deliberate v1 design choice for cleaner headers:

- "Evolucao mensal" (NOT "Poupanca - evolucao mensal")
- "Historico mensal" (NOT "Poupanca - historico mensal")
- "Matriz mensal" (NOT "Poupanca - matriz mensal")

### Chart colors

| Index     | Color          | Hex       | Secondary (acumulado_no_ano) | Hex       |
| --------- | -------------- | --------- | ---------------------------- | --------- |
| Poupanca  | emerald green  | `#10b981` | emerald-300                  | `#6ee7b7` |

The `acumulado_12m` line uses slate-400 (`#94a3b8`).

### Differences from `ddm/juros` v1.0

| Aspect                       | `juros` v1.0                                   | `poupanca` v1.0                                       |
| ---------------------------- | ---------------------------------------------- | ----------------------------------------------------- |
| Tab structure                | 4 tabs (3 index + Comparativo)                 | 1 tab (1 index, NO Comparativo)                       |
| Index count                  | 3 (Selic, Meta Selic, CDI)                     | 1 (Poupanca)                                          |
| Derivation                   | AVERAGE (mean of monthly cells)                | SUM (sum of monthly cells)                            |
| Numeric fields               | `month_value`, `media_no_ano`, `media_12m`     | `month_value`, `acumulado_no_ano`, `acumulado_12m`    |
| Catalog category             | `Juros`                                        | `Renda Fixa`                                          |
| Unit                         | `% a.a.` (annualized daily rate)               | `%` (monthly yield)                                   |
| Table `negative_red` flag    | No                                             | Yes (poupanca yields can be negative)                 |
| Section title prefix         | Yes (`{name} - evolucao mensal`)               | No (`Evolucao mensal`)                                |
| Overlay chart                | Yes (Comparativo tab)                          | No (only 1 index — nothing to overlay)                |
| `_heat_color` return type    | dict (v4 fix)                                  | dict (v1 fix from day one)                            |
| `build_matrix_table_section` | `type:"heatmap"` (v4 fix)                      | `type:"heatmap"` (v1 fix from day one)                |

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-poupanca` entry that
calls `data_sources.ddm.poupanca.sync_engine.sync_all(force=True)`. The
poupanca skill declares `REQUIRED_SOURCES = ["ddm"]` (auto-refreshes
inflation.db before dashboard run; the `ddm-poupanca` entry is available
for explicit invocation via `_trigger_sync("ddm-poupanca")`).

### Tests

- `tests/data_sources/ddm/poupanca/test_fetcher.py` — 12 tests covering
  `_parse_br_number`, `_parse_data_value`, `parse_matrix_only` (years,
  month header with NO "Ano", data values, empty HTML, stray "Ano"
  filter), and `flatten_matrix_to_observations` (sorting, missing-cell
  skip, month_value, acumulado_no_ano SUM, acumulado_12m SUM full +
  short window + year-boundary cross, plus an explicit SUM-not-AVERAGE
  regression test).
- `tests/skills/ddm/poupanca/test_dashboard.py` — 11 tests covering tab
  structure (1 tab only — NO Comparativo), subtabs structure (Histórico
  + Matriz), KPI promotion, 3-dataset chart, 4-column table with
  `negative_red=True`, NO "Ano" column in matrix, `type="heatmap"`
  section, `{text, bg, color}` cell dicts, Chart.js config emission,
  PT-BR formatting, section titles not repeating the index name.
