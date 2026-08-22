# DDM Dividends Skill

Skill: **`ddm/dividends`**
Mode: `dashboard` (1 tab)
Data source: `data_sources/ddm/dividends/` (read-only queries against
`memory_db/ddm/dividends.db`).

## Overview

A 1-tab dashboard for Brazilian corporate dividend events scraped from
dadosdemercado.com.br/agenda-de-dividendos.

### Dividendos tab

- **4 KPI cards** (promoted to top level):
  1. **Total de dividendos** — count of all dividend rows + per-tipo
     breakdown in the subtitle.
  2. **Valor total** — sum of all dividend values (R$).
  3. **Maior dividendo** — biggest single dividend (ticker + R$ value).
  4. **Proximo pagamento** — next payment date (DD/MM/YYYY PT-BR display).

- **Distribution chart** (grouped bar):
  - 2 datasets: Dividendo (teal `#0d9488`) + JCP (amber `#f59e0b`).
  - 8 value-range buckets on the X-axis:
    `<0,05` | `0,05-0,10` | `0,10-0,25` | `0,25-0,50` |
    `0,50-1,00` | `1,00-2,00` | `2,00-5,00` | `>=5,00`.
  - Y-axis: count of dividends per bucket.
  - Bars rendered side-by-side (grouped, NOT stacked).

- **Sortable dividends table**:
  - Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento.
  - Click any column header to re-sort; click again to toggle asc/desc.
  - Default sort: **Valor DESC** (column index 2, 0-indexed).
  - Numeric Valor cells carry `data-value="0.017250"` so the
    `sortTable()` JS can do accurate numeric sorting even with the
    `R$ 0,017250` display text.
  - Date cells display as `DD/MM/YYYY` (PT-BR) — stored as `YYYY-MM-DD`
    in the DB.
  - **NO price colors** on Valor (dividend amounts are always >= 0, not
    stock prices). The report builder explicitly omits `negative_red`,
    `price_colors`, and `cell_colors`.

## Why a 1-tab dashboard?

The dividend agenda is a single page of upcoming events (no time-series,
no per-ticker breakdown needed at the dashboard level). All the data fits
on one tab with KPIs + a distribution chart + the sortable table. Adding
more tabs would just split related views across tabs without benefit.

## Usage

```python
from skills.ddm.dividends import route as dividends_skill

# Full dashboard (auto-syncs ddm-dividends source if stale).
dividends_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
dividends_skill(mode="dashboard", skip_sync=True)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="dividends", mode="dashboard")
```

## Sortable table feature

The sortable-table feature shipped in the acoes commit (macros.html +
base.html + dashboard.html). To activate it on a table section:

```python
{
    "type": "table",
    "title": ...,
    "columns": [...],
    "rows": [[...], ...],
    "column_align": [...],
    "sortable": True,                              # activates th.sortable
    "sort_types": ["text", "text", "number", "text", "text", "text"],
    "default_sort": {"column": 2, "direction": "desc"},
}
```

The `macros.data_table` macro renders each `<th class="sortable"
data-sort-type="...">` with `onclick="sortTable(this, colIndex)"`. The JS
reads `data-value` from numeric `<td>`s for accurate sorting (e.g.
`<td data-value="0.017250">R$ 0,017250</td>`), and `textContent` for
text columns.

Numeric cells are emitted as `{"text": "R$ 0,017250", "data_value":
"0.017250"}` dicts so the macro can emit the `data-value` attribute.

## Chart colors

| Tipo       | Color  | Hex       |
| ---------- | ------ | --------- |
| Dividendo  | teal   | `#0d9488` |
| JCP        | amber  | `#f59e0b` |

## Sync guard

`REQUIRED_SOURCES = ["ddm-dividends"]` — the route wrapper checks the
freshness of the `ddm-dividends` source before each dispatch and triggers
a force-sync if stale (calls `data_sources.ddm.dividends.sync_engine.
sync_all(force=True)`).

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5 + 1 marker)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES`.             |
| `_registry.py`                    | `MODES` + `register_mode` (with standalone fallback).  |
| `helpers.py`                      | `format_brl` (6 vs 2 decimals), `format_int`,          |
|                                   | `format_pct`, `format_value`, `format_date`            |
|                                   | (YYYY-MM-DD -> DD/MM/YYYY PT-BR).                      |
| `report.py`                       | `build_kpi_card`, `build_dividends_table` (sortable),  |
|                                   | `build_distribution_chart` (grouped bar),              |
|                                   | `build_error_section`.                                 |
| `modes/__init__.py`               | Empty marker.                                          |
| `modes/dashboard.py`              | The 1-tab dashboard (single mode).                     |

## See also

- [`ddm/dividends/CHANGELOG.md`](ddm/dividends/CHANGELOG.md) — version history.
- [`ddm/dividends/ROADMAP.md`](ddm/dividends/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/dividends/API.md`](../../data_sources/ddm/dividends/API.md)
  — underlying data source API.
