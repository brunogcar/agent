# DDM Proventos Skill (ddm/dividends)

Skill: **`ddm/dividends`**
Mode: `dashboard` (4 tabs — v2)
Data source: `data_sources/ddm/dividends/` (read-only queries against
`memory_db/ddm/dividends.db`).

## Overview

A 4-tab dashboard for Brazilian corporate dividend events (proventos —
dividendos + JCP) scraped from
dadosdemercado.com.br/agenda-de-dividendos, split by asset class (B3
natives vs BDRs) and aggregated by empresa and by payment date.

### Why the BDR split? [v2]

BDRs (Brazilian Depositary Receipts — foreign companies' shares traded
on B3) have tickers ending in **"34"** (AAPL34, GDBR34...). The agenda
mixes them with B3 natives, and their payouts live in a different value
universe: the top BDR events pay R$ 1,70-6,32 per receipt while B3
natives top at ~R$ 1,13 — ~40% of the events are BDRs. A single flat
table hid that; every view now splits on `is_bdr(ticker)`.

### Top-level KPIs (6 — the WHOLE agenda)

1. **Total de Proventos** — count of all events + the B3/BDR and
   Dividendo/JCP splits in the subtitle.
2. **Empresas Pagadoras** — distinct tickers in the agenda.
3. **Valor Total** — sum of all per-share values (R$).
4. **Maior Provento** — biggest single event (ticker + value).
5. **Valor Mediano** — median per-share value (the center the BDR
   outliers don't pull).
6. **Próximo Pagamento** — next payment date (DD/MM/YYYY PT-BR display).

### Tab 1 — Proventos (the B3 natives, the "main display")

- **Distribution chart** (grouped bar):
  - 2 datasets: Dividendo (teal `#0d9488`) + JCP (amber `#f59e0b`).
  - 8 value-range buckets on the X-axis:
    `<0,05` | `0,05-0,10` | `0,10-0,25` | `0,25-0,50` |
    `0,50-1,00` | `1,00-2,00` | `2,00-5,00` | `≥5,00`.
  - Y-axis: count of events per bucket. Grouped, NOT stacked.
- **Dividendo vs JCP doughnut** — the at-a-glance tipo split.
- **Sortable agenda table**:
  - Columns: Código | Tipo | Valor (R$) | Registro | Ex | Pagamento.
  - Default sort: **Valor DESC**. Numeric Valor cells carry
    `data-value="0.017250"` for accurate JS sorting.
  - Dates display as `DD/MM/YYYY` (stored `YYYY-MM-DD` in the DB).
  - **NO price colors** on Valor (dividend amounts, not stock prices) —
    DPA range colors (salmon → mint → blue) instead.

### Tab 2 — BDRs (the *34 twin)

The same distribution scale (8 faixas, Dividendo vs JCP) + the agenda
table for the *34 tickers — the payout-per-receipt universe stretches
the distribution to the right (faixas 1,00-2,00 / 2,00-5,00 / ≥5,00)
while the B3 natives concentrate below R$ 1,00. BDR tickers get the
slate accent `#94a3b8` (deliberately neither teal nor amber so "é BDR"
can never be misread as a tipo).

### Tab 3 — Por Empresa ("quem paga?")

- **Top 10 Empresas — Valor Total** + **Top 10 — Nº de Eventos** bars,
  each bar colored by class (B3 teal / BDR slate).
- **Todas as Empresas table** — Empresa | Tipo (mix Div/JCP) | Eventos |
  Valor Total | Média | Máximo | Último Pagamento. Default sort: Valor
  Total DESC.

### Tab 4 — Calendário ("quando cai?")

- **Pagamentos por Dia** bar chart — one bar per payment date, **Pago**
  (teal) vs **A pagar** (amber, from today).
- **Calendário de Pagamentos table** — Data | Eventos | BDRs | Valor
  Total | Valor BDR | Principais Pagadores (the Data tooltip carries
  the day's top-3). Default sort: Data DESC.

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

## Shared numerics [v2]

`helpers.py` carries the aggregations used by BOTH this static
dashboard and the WebUI Mercado page's Proventos family
(`webui/services/dividendos.py`) — no forked numerics:

| Function                | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| `is_bdr(ticker)`        | True for `*34` tickers (the BDR predicate).        |
| `summarize(divs, today)`| Scoped KPIs: totals, by_tipo, biggest, next pay,   |
|                         | tickers, median/mean.                              |
| `bucketize(divs)`       | The 8 value-range buckets × tipo counts.           |
| `aggregate_by_empresa`  | Per-ticker: events, total/avg/max, last payment.   |
| `aggregate_by_day`      | Per-payment-date: events, value, BDR share, top-3. |

Plus the display helpers (`format_brl` 6-vs-2 decimals, `format_int`,
`format_pct`, `format_value`, `format_date`).

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

## Chart colors

| Element          | Color      | Hex       |
| ---------------- | ---------- | --------- |
| Dividendo        | teal       | `#0d9488` |
| JCP              | amber      | `#f59e0b` |
| BDR (classe)     | slate      | `#94a3b8` |
| Pago (calendário)| teal       | `#0d9488` |
| A pagar          | amber      | `#f59e0b` |

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
| `_registry.py`                    | `MODES` + `register_mode` (thin delegate to `skills._base`; Phase 4 C3 removed the pre-merge standalone fallback).  |
| `helpers.py`                      | Display helpers + the [v2] shared numerics            |
|                                   | (`is_bdr`, `summarize`, `bucketize`,                  |
|                                   | `aggregate_by_empresa`, `aggregate_by_day`).          |
| `report.py`                       | `build_kpi_card`, `build_dividends_table` (sortable), |
|                                   | `build_distribution_chart` (grouped bar),             |
|                                   | `build_tipo_doughnut`, `build_top_empresas_chart`,    |
|                                   | `build_empresa_table`, `build_calendario_chart`,      |
|                                   | `build_calendario_table`, `build_error_section`.      |
| `modes/__init__.py`               | Empty marker.                                          |
| `modes/dashboard.py`              | The 4-tab dashboard (single mode).                     |

## WebUI

The Mercado page's **Proventos** family (`/webui/mercado`, WebUI v1.18)
is the live twin of this dashboard: 4 lazy subtabs (Visão Geral / BDRs /
Por Empresa / Calendário) over the same query engine + shared numerics,
served by `GET /api/webui/mercado/sections/dividendos:<sub>`. Family
key `dividendos` (the data source's name — the company page owns the
`proventos:*` registry keys); display name "Proventos".

## See also

- [`ddm/dividends/CHANGELOG.md`](ddm/dividends/CHANGELOG.md) — version history.
- [`ddm/dividends/ROADMAP.md`](ddm/dividends/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/dividends/API.md`](../../data_sources/ddm/dividends/API.md)
  — underlying data source API.
