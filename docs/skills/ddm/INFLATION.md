# DDM Inflation Skill

Skill: **`ddm/inflation`**
Mode: `dashboard` (4 tabs)
Data source: `data_sources/ddm/inflation/` (read-only queries against
`memory_db/ddm/inflation.db`).

## Overview

A 4-tab dashboard for Brazilian inflation indices scraped from
dadosdemercado.com.br:

1. **IGP-M** — Índice Geral de Preços - Mercado (FGV).
2. **IPCA** — Índice Nacional de Preços ao Consumidor Amplo (IBGE).
3. **INPC** — Índice Nacional de Preços ao Consumidor (IBGE).
4. **Comparativo** — overlay of the 12-month acumulado for all 3 indices.

Each per-index tab carries 3 KPI cards (latest month variation, year
acumulado, 12m acumulado) and TWO subtabs (v3):

- **Histórico** — the evolução chart with 3 datasets (variação mensal %
  solid, acumulado no ano % dashed in the index's 300-shade, acumulado
  12m % dotted slate) + the history table (Mes/Ano | Índice do mês |
  Acumulado no ano | Acumulado 12m), DESC, right-aligned numeric columns.
- **Matriz** — the monthly matrix (year × Jan–Dez + Ano) as a HEATMAP
  (v2): diverging red→white→green for the monthly cells
  (negative/zero/positive), sequential white→blue for the "Ano" column;
  min/max computed from the actual data. The matrix is parsed from the
  live page (`monthly_matrix` — one HTTP call, 5-min cache; it is NOT
  stored in the DB).

Window phrasing (v3.1): `months=0` / `compare_months=0` (the defaults —
all available data) render "todo o histórico disponível" in the chart
description and the Comparativo title (was the "Últimos 0 meses" bug).

The Comparativo tab shows a single overlay chart (3 datasets, one per
index) of the 12m acumulado. It has **no tables**.

## Usage

```python
from skills.ddm.inflation import route as inflation_skill

# Full dashboard (auto-syncs ddm source if stale).
inflation_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
inflation_skill(mode="dashboard", skip_sync=True)

# Custom windows.
inflation_skill(mode="dashboard", months=24, compare_months=12)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="inflation", mode="dashboard")
```

## Chart colors

| Index | Color  | Hex       | Acum. ano (dashed) |
| ----- | ------ | --------- | ------------------ |
| IGP-M | blue   | `#3b82f6` | `#93c5fd`          |
| IPCA  | amber  | `#f59e0b` | `#fcd34d`          |
| INPC  | purple | `#a855f7` | `#d8b4fe`          |

The 12m line is slate `#94a3b8` for every index.

## Sync guard

`REQUIRED_SOURCES = ["ddm-inflation"]` — the route wrapper checks the
freshness of the source before each dispatch and triggers a force-sync
if stale. `skills/_base._trigger_sync.sync_map` calls
`data_sources.ddm.inflation.sync_engine.sync_all(force=True)`.

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## WebUI

The Mercado page's **Inflação family** (`/webui/mercado` — WebUI v1.15)
reorganizes this dashboard into 4 lazy subtabs (Visão Geral — the 3-index
comparison; IGP-M/IPCA/INPC — evolução + histórico + matriz) over the
SAME query engine (read-only against `inflation.db`; the matrix is
computed from the stored series, no live fetch). Service:
`webui/services/inflation.py`; adapters `inflacao:*` in
`webui/adapters/registry.py`.

## Files (5)

| File                              | Purpose                                                |
| -------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES`.             |
| `_registry.py`                    | `MODES` + `register_mode` (thin delegate to `skills._base`; Phase 4 C3 removed the pre-merge standalone fallback).  |
| `helpers.py`                      | `format_value`, `format_pct`, `compute_stats`, `build_observation_rows`, `_heat_color`. |
| `report.py`                       | `build_kpi_card`, `build_chart_section`,               |
|                                   | `build_overlay_chart_section`, `build_table_section`,  |
|                                   | `build_matrix_table_section`, `build_text_section`,    |
|                                   | `build_error_section`.                                 |
| `modes/dashboard.py`              | The 4-tab dashboard (single registered mode).          |

## See also

- [`ddm/inflation/CHANGELOG.md`](ddm/inflation/CHANGELOG.md) — version history.
- [`ddm/inflation/ROADMAP.md`](ddm/inflation/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/inflation/API.md`](../../data_sources/ddm/inflation/API.md)
  — underlying data source API.
