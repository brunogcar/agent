# DDM Inflation Skill

Skill: **`ddm/inflation`**
Mode: `dashboard` (4 tabs)
Data source: `data_sources/ddm/inflation/` (read-only queries against
`memory_db/ddm/inflation/inflation.db`).

## Overview

A 4-tab dashboard for Brazilian inflation indices scraped from
dadosdemercado.com.br:

1. **IGP-M** — Índice Geral de Preços - Mercado (FGV).
2. **IPCA** — Índice Nacional de Preços ao Consumidor Amplo (IBGE).
3. **INPC** — Índice Nacional de Preços ao Consumidor (IBGE).
4. **Comparativo** — overlay of the 12-month acumulado for all 3 indices.

Each per-index tab shows:

- 3 KPI cards (latest month variation, year acumulado, 12m acumulado).
- Historical chart with 2 datasets (monthly variation %, 12m acumulado %),
  last 60 months.
- History table (Mes/Ano | Indice do mes | Acumulado no ano | Acumulado 12m),
  right-aligned numeric columns.
- Monthly matrix table (year × Jan–Dez + Ano, right-aligned).

The Comparativo tab shows a single overlay chart (3 datasets, one per
index) of the 12m acumulado over the last 24 months. It has **no tables**.

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

| Index | Color  | Hex       |
| ----- | ------ | --------- |
| IGP-M | blue   | `#3b82f6` |
| IPCA  | amber  | `#f59e0b` |
| INPC  | purple | `#a855f7` |

## Sync guard

`REQUIRED_SOURCES = ["ddm"]` — the route wrapper checks the freshness of
the `ddm` source before each dispatch and triggers a force-sync if stale.
`skills/_base._trigger_sync.sync_map["ddm"]` calls
`data_sources.ddm.inflation.sync_engine.sync_all(force=True)`.

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES`.             |
| `_registry.py`                    | `MODES` + `register_mode` (with standalone fallback).  |
| `helpers.py`                      | `format_value`, `format_pct`, `compute_stats`.         |
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
