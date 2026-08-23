# DDM Inflation Skill — Changelog

## v1.0 — 2025-01

Initial release. Mirrors `bcb/macro` skill pattern.

### Added (5 files)

- `skills/ddm/inflation/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm"]`.
- `skills/ddm/inflation/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/inflation/helpers.py` — `format_value`, `format_pct`,
  `compute_stats`, `build_observation_rows`.
- `skills/ddm/inflation/report.py` — `build_kpi_card`,
  `build_chart_section` (2 datasets: month_value + acumulado_12m),
  `build_overlay_chart_section` (multi-index overlay for Comparativo tab),
  `build_table_section` (with `column_align`), `build_matrix_table_section`,
  `build_text_section`, `build_error_section`.
- `skills/ddm/inflation/modes/dashboard.py` — 4-tab dashboard.

### Dashboard: 4 tabs

1. **IGP-M** (group: Indices) — 3 KPIs (mes / ano / 12m) + historical
   chart (60m, 2 datasets) + history table + monthly matrix table.
2. **IPCA** (group: Indices) — same shape.
3. **INPC** (group: Indices) — same shape.
4. **Comparativo** (group: Analise) — overlay chart (acumulado_12m for
   all 3 indices, last 24 months), NO tables.

### Chart colors

| Index | Color     | Hex       |
| ----- | --------- | --------- |
| IGP-M | blue      | `#3b82f6` |
| IPCA  | amber     | `#f59e0b` |
| INPC  | purple    | `#a855f7` |

### Sync wiring

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm` entry that calls
`data_sources.ddm.inflation.sync_engine.sync_all(force=True)` when the
`ddm` source is stale. Tests bypass via `CVM_SKIP_SYNC=1`.

### Tests

- `tests/skills/ddm/inflation/test_dashboard.py` — 9 tests covering
  tab structure, KPI promotion, chart config, table column_align,
  PT-BR formatting, and overlay dataset count.
