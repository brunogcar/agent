# DDM Fluxo Skill

Skill: **`ddm/fluxo`**
Mode: `dashboard` (5 tabs)
Data source: `data_sources/ddm/fluxo/` (read-only queries against
`memory_db/ddm/fluxo.db`).

## Overview

A 5-tab dashboard for the Brazilian B3 investment flow (daily net inflow
/ outflow by investor type) scraped from dadosdemercado.com.br/fluxo:

1. **Fluxo** — KPIs (top-level) + daily bar chart with 4 investor
   datasets + sortable table of all daily observations.
2. **Estrangeiro** — 3 subtabs (Diario / Mensal / Anual).
3. **Institucional** — same.
4. **Pessoa física** — same.
5. **Inst. Financeira** — same.

### Fluxo tab (group: Fluxo)

The Fluxo tab has:

- **Bar chart** at the top showing 4 datasets (Estrangeiro, Institucional,
  Pessoa física, Inst. Financeira) × ~247 daily rows. Colors: blue
  (Estrangeiro), red (Institucional), amber (Pessoa física), green
  (Inst. Financeira). Range selector enabled (Tudo/10A/5A/1A/6M/3M/1M).
- **Sortable table** below the chart showing all daily observations:

  | Data | Estrangeiro | Institucional | Pessoa física | Inst. Financeira | Outros |

  - `sortable=True` + `default_sort = {"column": 0, "direction": "desc"}`
    (Data DESC = newest first).
  - `sort_types = ["text","number","number","number","number","number"]`.
  - `negative_red=True` (negative cells render in red).
  - Dates displayed as DD/MM/YYYY; numeric cells carry `data-value`
    attributes for accurate numeric sorting.

### Investor tabs (group: Investidores)

Each investor tab has 3 subtabs:

- **Diário** — daily bar chart (single dataset, green for positive days,
  red for negative) + sortable daily table (Data | Valor (mi)).
- **Mensal** — monthly cumulative line chart (sum of daily values per
  month, green for positive months, red for negative) + sortable monthly
  table.
- **Anual** — running annual cumulative line chart (each day = previous
  cumulative + today) + sortable cumulative table.

### KPIs (top-level, 5 cards)

| KPI                       | Source                                       | Example             |
| ------------------------- | -------------------------------------------- | ------------------- |
| Última data               | `summary().last_date`                        | `19/08/2026`        |
| Total Estrangeiro         | in-memory sum of `estrangeiro` column        | `R$ -3.860,52 mi`   |
| Total Institucional       | in-memory sum of `institucional` column      | `R$ 2.463,56 mi`    |
| Total Pessoa física       | in-memory sum of `pessoa_fisica` column      | `R$ 554,91 mi`      |
| Total Inst. Financeira    | in-memory sum of `inst_financeira` column    | `R$ 691,38 mi`      |

The "Total" KPIs are the cumulative net flow over the entire synced
period (~1 year). Negative totals (e.g. Estrangeiro) indicate net
outflow over the period.

## Why values are parsed to floats

Unlike the `ddm/focus` sub-domain (which stores PT-BR value strings
verbatim because the page mixes percentage, currency, and integer-count
columns), the fluxo page has a single unit (millions of R$) across all
5 value columns. Parsing to floats at the fetcher boundary:

1. Enables accurate numeric sorting in the table (the JS `sortTable()`
   reads `data-value` and sorts numerically, so -1582.35 sorts before
   -9.31, not after).
2. Enables SQL aggregations (monthly cumulative SUM, annual running
   cumulative) without re-parsing.
3. Enables Chart.js rendering directly (no `parse_numeric` helper
   needed at chart time).

The dashboard re-formats floats back to PT-BR display strings via
`format_brl` (in `skills/ddm/fluxo/helpers.py`):
- `-1582.35` → `"R$ -1.582,35 mi"`
- `1029.81` → `"R$ 1.029,81 mi"`
- `42.36` → `"R$ 42,36 mi"`

## Usage

```python
from skills.ddm.fluxo import route as fluxo_skill

# Full dashboard (auto-syncs ddm-fluxo source if stale).
fluxo_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
fluxo_skill(mode="dashboard", skip_sync=True)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="fluxo", mode="dashboard")
```

## Chart colors

The 4 investor datasets in the Fluxo tab use a fixed palette:

| Dataset          | Color  | Hex       |
| ---------------- | ------ | --------- |
| Estrangeiro      | blue   | `#3b82f6` |
| Institucional    | red    | `#ef4444` |
| Pessoa física    | amber  | `#f59e0b` |
| Inst. Financeira | green  | `#22c55e` |

The daily investor chart uses per-bar colors:

| Sign     | Color  | Hex       |
| -------- | ------ | --------- |
| positive | green  | `#22c55e` |
| negative | red    | `#ef4444` |

The monthly + annual cumulative charts use green for positive values
and red for negative values.

## Range selector

Charts that show a daily time series (Fluxo chart, Diario subtab chart,
Anual subtab chart) include a range selector with 7 buttons:

- Tudo (all data)
- 10A, 5A, 1A (10-year / 5-year / 1-year)
- 6M, 3M, 1M (6-month / 3-month / 1-month)

The template's `filterPriceChart` JS reads `price_range_selector` +
`price_full_labels` + `price_full_datasets` and re-renders the chart
with the filtered data. All 3 keys MUST be emitted together — missing
any one silently breaks the buttons.

The Mensal subtab chart does NOT have a range selector (monthly data is
~12 points per year — no need to filter).

## Sync guard

`REQUIRED_SOURCES = ["ddm-fluxo"]` — the route wrapper checks the
freshness of the `ddm-fluxo` source before each dispatch and triggers
a force-sync if stale (>24h or missing).

`skills/_base._trigger_sync.sync_map["ddm-fluxo"]` calls
`data_sources.ddm.fluxo.sync_engine.sync_all(force=True)` — re-fetches
the `/fluxo` page (with full Chrome 127 browser headers to bypass
CloudFront) and `INSERT OR REPLACE`s all rows.

`skills/_freshness.get_freshness()` includes a `ddm-fluxo` key so any
consumer can poll the last-sync timestamp for the fluxo DB.

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5 + modes/__init__.py)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES=["ddm-fluxo"]`. |
| `_registry.py`                    | `MODES` + `register_mode` (with standalone fallback).  |
| `helpers.py`                      | `format_brl` (PT-BR with "mi" suffix), `format_int`    |
|                                   | (PT-BR thousands), `format_pct`, `format_date`         |
|                                   | (YYYY-MM-DD → DD/MM/YYYY), `format_value`.             |
| `report.py`                       | `build_kpi_card`, `build_fluxo_table` (sortable +      |
|                                   | `data-value` cells + `negative_red=True`),             |
|                                   | `build_fluxo_chart` (4-dataset bar + range selector),  |
|                                   | `build_investor_daily_chart` (per-bar green/red +      |
|                                   | range selector), `build_investor_monthly_chart`,       |
|                                   | `build_investor_annual_chart` (line + range selector), |
|                                   | `build_investor_table` (2-column sortable +            |
|                                   | `negative_red=True`), `build_error_section`.           |
| `modes/dashboard.py`              | The 5-tab dashboard (single mode).                     |
| `modes/__init__.py`               | Modes package marker (for auto_discover).              |

## See also

- [`ddm/fluxo/CHANGELOG.md`](ddm/fluxo/CHANGELOG.md) — version history.
- [`ddm/fluxo/ROADMAP.md`](ddm/fluxo/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/fluxo/API.md`](../../data_sources/ddm/fluxo/API.md)
  — underlying data source API.
- [`../../data_sources/ddm/DDM.md`](../../data_sources/ddm/DDM.md) —
  DDM data source landing page (covers all 6 sub-domains).
