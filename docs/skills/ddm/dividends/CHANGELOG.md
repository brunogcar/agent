# DDM Dividends Skill — Changelog

## v2 — 2026-11 (WebUI v1.18)

The Proventos reorganization: the 1-tab flat dashboard becomes 4 tabs
with the **BDR split** (tickers ending in 34 — ~40% of the events,
payouts R$ 1,70-6,32 vs B3 natives topping at ~R$ 1,13) + the two
aggregations the flat table hid. PT-BR accents fixed in every
user-facing string (the v1 static's were ASCII-fied — the fix the acoes
skill got in its v2). Same data layer (`data_sources/ddm/dividends`
query engine, read-only).

### Added

- `helpers.py` — the SHARED NUMERICS (used by BOTH the static dashboard
  and the WebUI Mercado page's Proventos family via
  `webui/services/dividendos.py` — the no-forked-numerics pattern the
  acoes skill set in v1.17):
  - `is_bdr(ticker)` — the *34 predicate.
  - `summarize(divs, today_iso)` — scoped KPI numbers (totals, by_tipo,
    biggest, next payment, distinct tickers, median/mean).
  - `DISTRIBUTION_BUCKETS` + `bucketize(divs)` — the 8 value-range
    buckets × tipo counts (moved from report.py's inline loop; the
    ≥5,00 label gains the ≥ glyph).
  - `aggregate_by_empresa(divs)` — per-ticker: events, tipo split,
    total/avg/max value, biggest event, last payment, BDR flag.
  - `aggregate_by_day(divs)` — per-payment-date: events, value, BDR
    count/value, the day's top-3 payers.
- `report.py` — new builders: `build_tipo_doughnut` (Dividendo vs JCP),
  `build_top_empresas_chart` (Top 10 by value/events, B3 teal vs BDR
  slate datasets), `build_empresa_table` (per-empresa aggregation),
  `build_calendario_chart` (per-day bars, Pago vs A pagar vs today),
  `build_calendario_table` (per-day rows with top-3 payers). The BDR
  slate accent `#94a3b8` is deliberately neither teal nor amber so
  "é BDR" can never be misread as a tipo.
- `modes/dashboard.py` — the 4 tabs: **Proventos** (B3 natives:
  distribution + doughnut + sortable table), **BDRs** (the *34 twin),
  **Por Empresa** (Top 10 charts + the empresas table), **Calendário**
  (per-day chart + table). Top-level KPIs grow 4 → 6 (Empresas
  Pagadoras + Valor Mediano; the Total KPI carries the B3/BDR split).

### Changed

- PT-BR accents everywhere: "Código", "Distribuição por Faixa de
  Valor", "Próximo Pagamento", "Valor Mediano", "Calendário",
  "NÃO empilhadas" (was "Codigo", "Distribuicao", "Proximo"…).
- MANIFEST description refreshed (4 tabs, the BDR split, the
  aggregations).

## v1.0 — 2026-07

Initial release. Mirrors `ddm/inflation/juros/poupanca` skill pattern,
adapted for the single-page dividend agenda.

### Added (5 files + 1 marker)

- `skills/ddm/dividends/__init__.py` — MANIFEST + `route()` via
  `make_route()` with sync guard. `REQUIRED_SOURCES = ["ddm-dividends"]`.
- `skills/ddm/dividends/_registry.py` — `MODES` + `register_mode`
  (delegates to `skills._base` when merged, falls back to a minimal
  inline implementation for standalone testing).
- `skills/ddm/dividends/helpers.py` — `format_brl` (6 decimals for |v|<1.0,
  2 decimals for |v|>=1.0; matches the dividend value range R$0.006 to
  R$7.96), `format_int` (PT-BR thousands separators), `format_pct`,
  `format_value` (dispatch on unit), `format_date` (YYYY-MM-DD ->
  DD/MM/YYYY PT-BR display).
- `skills/ddm/dividends/report.py` — `build_kpi_card`,
  `build_dividends_table` (sortable=True with sort_types +
  default_sort={column: 2, direction: "desc"} + Valor cells as
  {"text", "data_value"} dicts + NO negative_red + NO price_colors +
  dates displayed as DD/MM/YYYY), `build_distribution_chart` (grouped
  bar with 2 datasets Dividendo teal #0d9488 + JCP amber #f59e0b, 8
  value-range buckets), `build_error_section`, `_format_count`.
- `skills/ddm/dividends/modes/__init__.py` — empty marker.
- `skills/ddm/dividends/modes/dashboard.py` — 1-tab dashboard.

### Dashboard: 1 tab (Dividendos)

The Dividendos tab contains:

1. **4 KPI cards** at top level:
   - Total de dividendos (count + per-tipo subtitle).
   - Valor total (sum of all values, formatted as R$).
   - Maior dividendo (biggest single dividend — ticker + value in
     subtitle).
   - Proximo pagamento (next payment date, DD/MM/YYYY PT-BR).

2. **Distribution chart** (grouped bar):
   - 2 datasets side-by-side: Dividendo (teal #0d9488) + JCP (amber
     #f59e0b).
   - 8 value-range buckets on X-axis: <0,05 | 0,05-0,10 | 0,10-0,25 |
     0,25-0,50 | 0,50-1,00 | 1,00-2,00 | 2,00-5,00 | >=5,00.
   - Y-axis: count of dividends per bucket.

3. **Sortable dividends table**:
   - Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento.
   - column_align: left, left, right, right, right, right.
   - sortable=True.
   - sort_types: text, text, number, text, text, text.
   - default_sort: {column: 2 (Valor), direction: "desc"}.
   - Each Valor cell is a dict {"text": "R$ 0,017250", "data_value":
     "0.017250"} so the macros.html data_table macro can emit
     `<td data-value="0.017250">R$ 0,017250</td>`.
   - Dates displayed as DD/MM/YYYY (PT-BR).
   - NO negative_red, NO price_colors, NO cell_colors (dividend amounts,
     not stock prices).

### Chart colors

| Tipo       | Color  | Hex       |
| ---------- | ------ | --------- |
| Dividendo  | teal   | `#0d9488` |
| JCP        | amber  | `#f59e0b` |

### Differences from `ddm/juros` v1.0 + `ddm/poupanca` v1.0

| Aspect                       | `juros` / `poupanca` v1.0                | `dividends` v1.0                                   |
| ---------------------------- | ---------------------------------------- | -------------------------------------------------- |
| Tab structure                | Subtabs (Historico + Matriz)             | Flat (1 tab, no subtabs)                           |
| Chart type                   | Line chart (3 datasets: month_value + 2 derived) | Grouped bar chart (2 datasets: Dividendo + JCP) |
| Table type                   | Plain table + heatmap (Matriz)           | Sortable table (no heatmap)                        |
| KPI count                    | 3 per index (month_value + 2 derived)    | 4 (total, valor total, maior, proximo pagamento)  |
| Sortable table               | No                                       | Yes (shipped in acoes commit)                      |
| Date display                 | "Jul/2026" (Mês/Ano)                     | "01/07/2026" (DD/MM/YYYY)                          |
| Negative-red coloring        | poupanca only (yields can be negative)   | No (dividend amounts always >= 0)                  |

### Sync wiring

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm-dividends` entry
that calls `data_sources.ddm.dividends.sync_engine.sync_all(force=True)`.
The dividends skill declares `REQUIRED_SOURCES = ["ddm-dividends"]` so
the sync guard auto-refreshes the dividends DB before each dashboard run.

### Freshness tracking

`skills/_freshness.py` (and the mirrored `skills/cvm/_freshness.py` for
the cvm-subfolder layout) gained a `ddm-dividends` entry that reads
`synced_at` from the dividends DB's `sync_state` table.

### Tests

- `tests/data_sources/ddm/dividends/test_fetcher.py` — 12 tests covering
  `_parse_br_number`, `_parse_br_date`, `_extract_ticker`, and
  `parse_dividends_table` (row count, shape, first row values, JCP row,
  value range extremes, no-anchor fallback, empty HTML, no-table,
  short-row skip, table-by-class preference).
- `tests/skills/ddm/dividends/test_dashboard.py` — 18 tests covering tab
  structure (1 tab + group), KPI labels + values + PT-BR formatting,
  distribution chart (grouped bar, 8 buckets, bucket counts, colors),
  sortable table (6 columns, column_align, sort_types, default_sort,
  no negative_red/price_colors, dates as PT-BR, Valor cells as dicts
  with data_value, small vs large value formatting, ticker+tipo as plain
  strings), error-path graceful degradation.
