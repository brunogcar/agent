# DDM Focus Skill — Changelog

## v1.0 — 2025-01

Initial release. 13-tab dashboard with multi-subtab structure per tab.

### Added (5 files + modes/__init__.py)

- `skills/ddm/focus/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm-focus"]`
  (own source key — separate from `ddm` (inflation), `ddm-juros`,
  `ddm-poupanca`, and `ddm-acoes`).
- `skills/ddm/focus/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/focus/helpers.py` — `format_value(v)` (verbatim display),
  `format_int(v)` (PT-BR thousands), `comparison_symbol(c)` (▲ / ▼ / =),
  `comparison_color(c)` (green / red / gray), `parse_numeric(v)`
  (PT-BR string → float, for chart builder only).
- `skills/ddm/focus/report.py` — `build_kpi_card`, `build_year_table`
  (sortable: `sortable=True` + `default_sort={"column": 0, "direction":
  "asc"}` (Indicador ASC) + `sort_types=["text","text","text","text",
  "text","number"]` + per-cell `{"text": ..., "data-value": ...}` dict
  for numeric cells + colored Comp. cell `{"text": "▲", "color":
  "#22c55e"}`), `build_indicator_table` (sortable: Ano number sort
  `sort_types=["number","text","text","text","text","number"]`),
  `build_indicator_chart` (Chart.js grouped bar with 3 datasets:
  Há 4 semanas teal, 1 sem amber, Hoje blue; X-axis = years 2026-2029),
  `build_error_section`.
- `skills/ddm/focus/modes/dashboard.py` — 13-tab dashboard.
- `skills/ddm/focus/modes/__init__.py` — modes package marker.

### Dashboard: 13 tabs

1. **Focus** (group: Boletim) — 4 year subtabs (2026, 2027, 2028, 2029).
   Each subtab shows a year table with 12 indicator rows. Top-level KPIs
   are promoted from `summary()`.

2-13. **Per indicator** (group: Indicadores) — One tab per indicator
   (IPCA, PIB Total, Câmbio, Selic, IGP-M, IPCA Adm, Conta corrente,
   Balança comercial, Investimento direto no país, Dívida líquida setor
   pub, Resultado primário, Resultado nominal). Each tab has:
   - A grouped bar chart at the top (3 datasets × 4 years).
   - 3 subtabs (Há 4 semanas / 1 sem / Hoje), each showing a per-year
     table.

### Section titles (no skill-name prefix)

Section titles do NOT prefix with the skill name (already in tab name)
— a deliberate v1 design choice for cleaner headers (mirrors the
`ddm/acoes` + `ddm/poupanca` convention):

- "Indicadores - 2026" (year table — the year is in the subtab name
  but the table title repeats it for context)
- "Evolucao das expectativas - IPCA" (chart)
- "IPCA - Hoje" (indicator subtab table)

### Sync wiring

`skills/_base.py._trigger_sync.sync_map` gained a `ddm-focus` entry
that calls `data_sources.ddm.focus.sync_engine.sync_all(force=True)`.
The focus skill declares `REQUIRED_SOURCES = ["ddm-focus"]` so the
sync guard auto-refreshes `focus.db` before each dashboard run.

`skills/_freshness.py` also gained a `ddm-focus` entry in
`get_freshness()` so consumers can poll the last-sync timestamp for
any DDM sub-domain from a single dict.

### Tests

- `tests/data_sources/ddm/focus/test_fetcher.py` — 18 tests covering
  `_parse_int`, `_normalize_comparison`, `_strip_html`,
  `_find_year_for_table`, `parse_focus_tables` (rows per table, year
  extraction, value-string preservation, currency preservation,
  comparison normalization, empty HTML, malformed-row skip,
  header-repeat skip, h3 year heading).
- `tests/skills/ddm/focus/test_dashboard.py` — 24 tests covering tab
  structure (13 tabs: 1 Focus + 12 indicators), tab groups (Boletim /
  Indicadores), Focus tab 4 year subtabs, indicator tab 3 time-window
  subtabs + chart, KPI promotion (4 top-level KPIs), year table
  sortable features, indicator table sortable features, chart structure
  (3 datasets + labels + colors + X-axis + data-points + bar type).
