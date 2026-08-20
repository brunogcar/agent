# DDM Poupanca Skill

Skill: **`ddm/poupanca`**
Mode: `dashboard` (1 tab with subtabs, NO Comparativo — only 1 index)
Data source: `data_sources/ddm/poupanca/` (read-only queries against
`memory_db/ddm/poupanca.db`).

## Overview

A 1-tab dashboard for the Brazilian savings-account (caderneta de poupanca)
monthly yield scraped from dadosdemercado.com.br:

1. **Poupanca** — rendimento mensal da caderneta de poupanca. Monthly yield
   (% return for that month).

The tab uses `type:"subtabs"` with 2 subtabs:

### Historico subtab

- 3 KPI cards (latest month_value, acumulado_no_ano, acumulado_12m) —
  promoted to top level.
- Historical chart with **3 datasets**:
  1. `month_value` (solid line, emerald green `#10b981`)
  2. `acumulado_no_ano` (dashed line, emerald-300 `#6ee7b7`)
  3. `acumulado_12m` (dashed line, slate-400 `#94a3b8`)
- History table (Mês/Ano | Rendimento (%) | Acumulado no ano (%) |
  Acumulado 12m (%)), DESC order, right-aligned numeric columns,
  `negative_red=True` (poupanca yields can be negative during high-inflation
  periods).

### Matriz subtab

- Monthly matrix table (year × Jan..Dez, **NO** "Ano" column — these are
  monthly yields, not cumulative values).
- Heatmap rendering: all 12 month columns use a **diverging
  red→white→green** color scale based on the cell value vs the matrix
  min/max (low yields in red, high yields in green, midpoint in white).

## NO Comparativo tab

Poupanca has only 1 index in the catalog, so there is nothing to overlay.
The dashboard has 1 tab only (NO Comparativo tab). If a second index is
added to `POUPANCA_CATALOG` in the future, a Comparativo tab can be added
following the `ddm/juros` pattern (see
[`../JUROS.md`](JUROS.md)).

## Why derived (not raw)?

The poupanca page ships ONLY the monthly matrix (`id="index-values"`).
There is no historical table on the page and no "Ano" acumulado column.
The historical series is **derived** at parse time from the matrix:

- `month_value`        = cell value (monthly yield % for that month)
- `acumulado_no_ano`   = SUM of all months in same year UP TO that month
                        (year-to-date cumulative return)
- `acumulado_12m`      = SUM of the last 12 months INCLUDING current (rolling)

These match the Google Sheet formulas used by the original analyst:

- "Acumulado no ano (%)":     `SUM(FILTER(B:B, YEAR(A:A)=YEAR(d), A:A<=d))`
- "Acumulado 12 meses (%)":   `SUM(FILTER(B:B, A:A<=d, A:A>=d-365))`

For the first 11 months of the catalog, `acumulado_12m` uses the available
months (NOT None) — matches the Google Sheet behavior.

## SUM vs AVERAGE (key difference from juros)

Poupanca uses **SUM** for the derived acumulados; juros uses **AVERAGE**.
This is because the poupanca monthly yield is a percentage return (e.g.
0,67% means a 0.67% return that month) — summing monthly returns produces
the cumulative return over the period (e.g. 12 months × ~0.6%/month ≈
7.2%/year). Juros monthly cells are daily rates quoted as annualized % —
averaging produces the period-average rate.

This matches the analyst's Google Sheet layout (SUM formulas for poupanca,
AVERAGE formulas for juros).

## Usage

```python
from skills.ddm.poupanca import route as poupanca_skill

# Full dashboard (auto-syncs ddm source if stale).
poupanca_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
poupanca_skill(mode="dashboard", skip_sync=True)

# Custom window.
poupanca_skill(mode="dashboard", months=24)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="poupanca", mode="dashboard")
```

## Chart colors

| Index     | Color          | Hex       |
| --------- | -------------- | --------- |
| Poupanca  | emerald green  | `#10b981` |

The dashed `acumulado_no_ano` line uses emerald-300 (`#6ee7b7`); the dashed
`acumulado_12m` line uses slate-400 (`#94a3b8`).

## Section titles

Section titles do NOT prefix with the index name (already in the tab name):

- "Evolucao mensal" (NOT "Poupanca - evolucao mensal")
- "Historico mensal" (NOT "Poupanca - historico mensal")
- "Matriz mensal" (NOT "Poupanca - matriz mensal")

This is a deliberate v1 design choice — juros v1 used the prefix; poupanca
drops it for cleaner section headers.

## Sync guard

`REQUIRED_SOURCES = ["ddm"]` — the route wrapper checks the freshness of
the `ddm` source before each dispatch and triggers a force-sync if stale
(this currently triggers `ddm/inflation`'s sync_all). A separate
`skills/_base._trigger_sync.sync_map["ddm-poupanca"]` entry calls
`data_sources.ddm.poupanca.sync_engine.sync_all(force=True)` and is available
for explicit invocation via `_trigger_sync("ddm-poupanca")` (e.g. for manual
sync flows or tests).

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5 + modes/__init__.py)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES`.             |
| `_registry.py`                    | `MODES` + `register_mode` (with standalone fallback).  |
| `helpers.py`                      | `format_value`, `format_pct`, `compute_stats`,         |
|                                   | `_format_mes_ano`, `_heat_color` (returns dict,        |
|                                   | NOT string), `build_observation_rows`.                 |
| `report.py`                       | `build_kpi_card`, `build_chart_section` (3 datasets),  |
|                                   | `build_table_section` (negative_red=True),             |
|                                   | `build_matrix_table_section` (type="heatmap" with      |
|                                   | {text, bg, color} cell dicts, NO "Ano" column),        |
|                                   | `build_text_section`, `build_error_section`.           |
|                                   | NO `build_overlay_chart_section` (no Comparativo tab). |
| `modes/dashboard.py`              | The 1-tab dashboard with subtabs (single mode).        |
| `modes/__init__.py`               | Modes package marker (for auto_discover).              |

## See also

- [`ddm/poupanca/CHANGELOG.md`](ddm/poupanca/CHANGELOG.md) — version history.
- [`ddm/poupanca/ROADMAP.md`](ddm/poupanca/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/poupanca/API.md`](../../data_sources/ddm/poupanca/API.md)
  — underlying data source API.
