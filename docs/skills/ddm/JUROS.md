# DDM Juros Skill

Skill: **`ddm/juros`**
Mode: `dashboard` (4 tabs with subtabs)
Data source: `data_sources/ddm/juros/` (read-only queries against
`memory_db/ddm/juros.db`).

## Overview

A 4-tab dashboard for Brazilian interest-rate indices scraped from
dadosdemercado.com.br:

1. **Selic** — Taxa Selic diária (BCB). Daily average rate of bank reserves
   trades, annualized.
2. **Meta Selic** — Meta para a taxa Selic definida pelo Copom (Comitê de
   Política Monetária).
3. **CDI** — Certificado de Depósito Interbancário. Daily average rate of
   interbank financing, annualized.
4. **Comparativo** — overlay of the daily rate (`month_value`) for all 3
   indices.

Each per-index tab uses `type:"subtabs"` with 2 subtabs:

### Histórico subtab

- 3 KPI cards (latest month_value, media_no_ano, media_12m) — promoted to
  top level.
- Historical chart with **3 datasets** (not 2 like inflation):
  1. `month_value` (solid line, INDEX_COLORS[slug])
  2. `media_no_ano` (dashed line, lighter index color)
  3. `media_12m` (dashed line, slate gray)
- History table (Mês/Ano | Índice do mês (%) | Média no ano (%) | Média
  12 meses (%)), DESC order, right-aligned numeric columns.

### Matriz subtab

- Monthly matrix table (year × Jan..Dez, **NO** "Ano" column — these are
  daily rates, not cumulative variations).
- Heatmap rendering: all 12 month columns use a **diverging
  red→white→green** color scale based on the cell value vs the matrix
  min/max (low rates in red, high rates in green, midpoint in white).

The Comparativo tab shows a single overlay chart (3 datasets, one per
index) of the daily rate over the last 24 months. It has **no tables**.

## Why derived (not raw)?

Unlike inflation pages, juros pages ship ONLY the monthly matrix
(`id="index-values"`). There is no historical table on the page and no
"Ano" acumulado column. The historical series is **derived** at parse
time from the matrix:

- `month_value`   = cell value (daily rate % for that month)
- `media_no_ano`  = AVG of all months in same year UP TO that month
                   (year-to-date average)
- `media_12m`     = AVG of the last 12 months INCLUDING current (rolling)

These match the Google Sheet formulas used by the original analyst:

- "Média no ano (%)":     `AVERAGE(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`
- "Média 12 meses (%)":   `AVERAGE(FILTER(B:B, A:A<=d, A:A>=d-365))`

For the first 11 months of the catalog, `media_12m` uses the available
months (NOT None) — matches the Google Sheet behavior.

## Usage

```python
from skills.ddm.juros import route as juros_skill

# Full dashboard (auto-syncs ddm source if stale).
juros_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
juros_skill(mode="dashboard", skip_sync=True)

# Custom windows.
juros_skill(mode="dashboard", months=24, compare_months=12)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="juros", mode="dashboard")
```

## Chart colors

| Index      | Color  | Hex       |
| ---------- | ------ | --------- |
| Selic      | teal   | `#0d9488` |
| Meta Selic | blue   | `#3b82f6` |
| CDI        | amber  | `#f59e0b` |

Each index also uses a lighter secondary color (300-shade) for the
dashed `media_no_ano` line in the Histórico chart.

## Sync guard

`REQUIRED_SOURCES = ["ddm"]` — the route wrapper checks the freshness of
the `ddm` source before each dispatch and triggers a force-sync if stale
(this currently triggers `ddm/inflation`'s sync_all). A separate
`skills/_base._trigger_sync.sync_map["ddm-juros"]` entry calls
`data_sources.ddm.juros.sync_engine.sync_all(force=True)` and is available
for explicit invocation via `_trigger_sync("ddm-juros")` (e.g. for manual
sync flows or tests).

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES`.             |
| `_registry.py`                    | `MODES` + `register_mode` (thin delegate to `skills._base`; Phase 4 C3 removed the pre-merge standalone fallback).  |
| `helpers.py`                      | `format_value`, `format_pct`, `compute_stats`,         |
|                                   | `_format_mes_ano`, `_heat_color`,                      |
|                                   | `build_observation_rows`.                              |
| `report.py`                       | `build_kpi_card`, `build_chart_section` (3 datasets),  |
|                                   | `build_overlay_chart_section`, `build_table_section`,  |
|                                   | `build_matrix_table_section` (heatmap, NO "Ano"),      |
|                                   | `build_text_section`, `build_error_section`.           |
| `modes/dashboard.py`              | The 4-tab dashboard with subtabs (single mode).        |

## See also

- [`ddm/juros/CHANGELOG.md`](ddm/juros/CHANGELOG.md) — version history.
- [`ddm/juros/ROADMAP.md`](ddm/juros/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/juros/API.md`](../../data_sources/ddm/juros/API.md)
  — underlying data source API.
