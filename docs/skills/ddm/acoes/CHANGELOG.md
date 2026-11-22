# DDM Acoes Skill — Changelog

## v2 — 2026-11-22 (shipped with WebUI v1.17)

The EVOLUTION release: the /acoes page is a live quote table with NO
history (unlike inflation/juros/poupanca, whose pages carry full series),
so the only way to chart the price distribution over time is to
accumulate one snapshot per sync ourselves. The data source now stores
that history (`stocks_history`) and the dashboard charts it.

### Added — evolution store (data layer)

- `data_sources/ddm/acoes/catalog.py` — new `stocks_history` table (PK
  `(ref_date, ticker)` + index on `ref_date`; created by the same
  `CREATE TABLE IF NOT EXISTS` on every sync — the whole migration for
  pre-v2 DBs).
- `data_sources/ddm/acoes/sync_engine.py` — every `sync_all()` appends
  the day's rows to `stocks_history` (same-day re-syncs REPLACE that
  day's snapshot, a new day ADDS one), inside the SAME transaction as
  the main stocks INSERT (the new `extra_write_fn` hook in
  `data_sources/ddm/_base/sync_base.py`). The FIRST sync after
  upgrading a pre-v2 DB also preserves the previous `stocks` snapshot
  (read before the full-refresh DELETE) — the evolution starts with the
  data the user already has.
- `data_sources/ddm/acoes/query_engine.py` — `price_history(limit)`:
  every stored snapshot's prices grouped by ref_date (ASC; `limit` is
  per-DATE). Empty history is NOT an error (callers fall back to the
  current snapshot).
- `data_sources/ddm/acoes/__init__.py` — new `history` mode (exposes
  `price_history` through the data_source dispatcher).
- `data_sources/ddm/acoes/status_reporter.py` — `history_rows` +
  `history_dates` in the status dict.

### Added — evolution charts (dashboard)

- `skills/ddm/acoes/helpers.py` — `distribution_snapshots(dates,
  prices_by_date)`: buckets every snapshot into the shared 22-range
  palette (counts + shares that sum to EXACTLY 100 per date — the
  rounding drift rides the largest band). Used by the skill's static
  dashboard AND the WebUI Ações family (one bucketing, no forked
  numerics). Also `_format_data` (ISO → dd/mm/aaaa).
- `skills/ddm/acoes/report.py` — `build_evolution_sections`: TWO
  stacked-area charts over the snapshot dates — % do total (100%
  stacked, the reference-chart style) + nº de ações (absolute) — one
  dataset per range in the palette's color, lowest prices at the
  bottom, `interaction: nearest` (a 22-band index tooltip would be a
  wall), both with the Tudo/10A/…/1M range selector.
  `build_history_note_section`: <2 snapshots degrade to a text note
  explaining how the history accumulates.
- `skills/ddm/acoes/modes/dashboard.py` — evolution after the stocks
  table; empty history falls back to the CURRENT snapshot as the first
  point (exactly what the next sync preserves).

### Fixed — PT-BR + stale counts

- Every user-facing string now carries proper PT-BR accents ("Ações",
  "Distribuição de Preços", "Negócios", "Última (R$)", "Variação",
  "Número de Ações"…) — the juros/inflation statics always did; the
  acoes v1 strings were ASCII-fied.
- Stale "16 colored bars" docstrings/descriptions → 22 ranges (the
  palette's v2 added the 100–300+ blue tail); `skills/_price_colors.py`
  path references → `skills/_colors/price.py` (migrated module).

### Docs

- `docs/skills/ddm/ACOES.md` refreshed (22 ranges + new module path +
  the stocks_history evolution section + the WebUI v1.17 note).

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

`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` gained a `ddm-acoes` entry that
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
