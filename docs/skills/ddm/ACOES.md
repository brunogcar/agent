# DDM Acoes Skill

Skill: **`ddm/acoes`**
Mode: `dashboard` (1 tab, no subtabs)
Data source: `data_sources/ddm/acoes/` (read-only queries against
`memory_db/ddm/acoes.db`).

## Overview

A 1-tab dashboard for the Brazilian B3 listed stocks scraped from
dadosdemercado.com.br/acoes:

1. **Ações** — all B3 listed stocks (~380 rows). KPIs at top, price
   distribution chart, sortable stocks table, and [v2] the evolution of
   the distribution over time.

### KPIs (top-level, 4 cards)

| KPI             | Source                  | Example               |
| --------------- | ----------------------- | --------------------- |
| Total de Ações  | `summary().total`       | `382`                 |
| Mais Negociada  | `summary().most_traded` | `PETR4` (Petrobras)   |
| Maior Alta      | `summary().biggest_gainer` | `+8,45%` (PETR4)   |
| Maior Baixa     | `summary().biggest_loser`  | `-12,30%` (BEEF3)  |

### Sortable stocks table

Columns: `Ticker` | `Nome` | `Negócios` | `Última (R$)` | `Variação`

| Feature          | Value                                                  |
| ---------------- | ------------------------------------------------------ |
| `sortable`       | `True` (click headers to sort asc/desc)                |
| `default_sort`   | `{"column": 2, "direction": "desc"}` (Negócios DESC)  |
| `sort_types`     | `["text", "text", "number", "number", "number"]`       |
| `column_align`   | `["left", "left", "right", "right", "right"]`          |
| `negative_red`   | `True` (negative variations render in red)             |
| Numeric cells    | `{"text": "R$ 44,30", "data-value": "44.300000"}`      |
| Variation cells  | `{"text": "+2,78%", "data-value": "2.780000"}`         |

Each numeric cell carries a `data-value` attribute with the raw float /
int so the JS `sortTable()` function can sort numerically without
parsing the PT-BR display text (which has `R$` prefix, `%` suffix,
thousands separators).

Default sort: **Negócios DESC** (column index 2). This mirrors the DDM
page's pre-sort — most-traded stocks appear first.

### Price-distribution chart

A Chart.js **bar chart** showing the distribution of all stock prices
across 22 ranges:

- X-axis: price-range labels (`X < 1`, `1 ≤ X < 2`, ..., `X ≥ 300`)
- Y-axis: number of tickers in that range
- Bar colors: each bar uses the corresponding range's color from
  `skills/_colors/price.py` (red → pink → yellow → green → teal → blue
  — the palette's v2 added the 100–300+ blue tail on top of the
  original 16 ranges)

The chart is a single-glance view of where B3 prices cluster (most
stocks trade below R$50). The palette is shared with any other skill
that displays stock prices, so visual consistency is centralized.

### Evolution of the distribution over time [v2]

The /acoes page is a **live quote table** — it carries no history. The
evolution comes from the snapshots the sync engine accumulates in
`stocks_history` (one per sync day; see below):

- **Evolução da Distribuição — % do Total**: a 100% stacked area chart —
  one band per price range in the palette's color (lowest prices at the
  bottom), one column per stored snapshot, bands summing to exactly
  100% on every date. The reference-chart style for distribution
  monitoring.
- **Evolução da Distribuição — Nº de Ações**: the same series in
  absolute counts (the stacked total is the number of listed stocks on
  each date — delistings shrink the top).

Both use `interaction: nearest` (a 22-band index tooltip would be a
wall of rows) and carry the Tudo/10A/…/1M range selector. The shared
numerics live in `helpers.distribution_snapshots()` (counts + exact-100
shares) — the same function the WebUI Ações family uses.

Fewer than 2 stored snapshots degrade to a text note explaining how the
history accumulates (the empty case falls back to the CURRENT stocks
snapshot as the first point — exactly what the next sync preserves).

## Why a flat page (not per-index)?

Unlike the other DDM sub-domains (`inflation` / `juros` / `poupanca`),
which fetch per-index pages and store historical series, the acoes page
is a SINGLE page with a SINGLE table of stock snapshots:

- No per-index slugs (the URL is just `/acoes`, not `/acoes/{slug}`)
- No history FROM the page (a live quote table — but since v2 every
  sync APPENDS the day's snapshot to `stocks_history`, so the
  distribution-over-time series grows one point per sync day)
- No matrix (no year × month grid)
- `stocks` primary key is `ticker` (not `(slug, ref_date)`);
  `stocks_history` (the evolution store) is keyed `(ref_date, ticker)`

The dashboard therefore has 1 tab (not 1 per index + Comparativo), no
subtabs, a flat sortable table (no heatmap) — plus the v2 evolution
charts.

### The evolution store (`stocks_history`) [v2]

| Aspect            | Behavior                                                    |
| ----------------- | ----------------------------------------------------------- |
| Written by        | every `sync_all()`, in the SAME transaction as `stocks`      |
| Key               | `(ref_date, ticker)` — one row per ticker per snapshot day   |
| Same-day re-sync  | REPLACES that day's snapshot (idempotent)                    |
| New-day sync      | ADDS one snapshot                                            |
| First sync after upgrade | also preserves the previous `stocks` snapshot (read before the full-refresh DELETE) — the evolution starts with the data the user already has |
| Migration         | `CREATE TABLE IF NOT EXISTS` on every sync — pre-v2 DBs need nothing manual |
| Read API          | `query_engine.price_history(limit)` / data-source mode `history` (limit is per-DATE, newest kept) |

## Usage

```python
from skills.ddm.acoes import route as acoes_skill

# Full dashboard (auto-syncs ddm-acoes source if stale).
acoes_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
acoes_skill(mode="dashboard", skip_sync=True)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="acoes", mode="dashboard")
```

## Section titles

Section titles do NOT prefix with the skill name (already in tab name):

- "Ações B3" (the stocks table — kept as-is because it identifies the
  source, not the skill)
- "Distribuição de Preços" (the chart)
- "Evolução da Distribuição — % do Total" / "— Nº de Ações" (the v2
  evolution charts)

This is a deliberate v1 design choice — mirrors the `ddm/poupanca`
section-title convention.

## Sync guard

`REQUIRED_SOURCES = ["ddm-acoes"]` — the route wrapper checks the
freshness of the `ddm-acoes` source before each dispatch and triggers
a force-sync if stale (>24h or missing).

`skills/_base._trigger_sync.sync_map["ddm-acoes"]` calls
`data_sources.ddm.acoes.sync_engine.sync_all(force=True)` — re-fetches
the `/acoes page`, `INSERT OR REPLACE`s all rows AND appends the day's
snapshot to `stocks_history` (the evolution store).

`skills/_freshness.get_freshness()` includes a `ddm-acoes` key so any
consumer can poll the last-sync timestamp for the acoes DB.

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Price-range palette

The 22-range palette is centralized in `skills/_colors/price.py`
(migrated from the legacy `skills/_price_colors.py`):

| Range             | Color     | Text |
| ----------------- | --------- | ---- |
| `X < 1`           | `#dc2626` | white |
| `1 ≤ X < 2`       | `#ef4444` | white |
| `2 ≤ X < 5`       | `#f8bbd0` | black |
| `5 ≤ X < 10`      | `#fce4ec` | black |
| `10 ≤ X < 15`     | `#fff9c4` | black |
| `15 ≤ X < 20`     | `#ffee58` | black |
| `20 ≤ X < 25`     | `#ffeb3b` | black |
| `25 ≤ X < 30`     | `#fdd835` | black |
| `30 ≤ X < 40`     | `#c8e6c9` | black |
| `40 ≤ X < 50`     | `#a5d6a7` | black |
| `50 ≤ X < 60`     | `#66bb6a` | white |
| `60 ≤ X < 70`     | `#43a047` | white |
| `70 ≤ X < 80`     | `#2e7d32` | white |
| `80 ≤ X < 90`     | `#1b5e20` | white |
| `90 ≤ X < 100`    | `#0d9488` | white (teal "neon" outlier) |
| `100 ≤ X < 125`   | `#1e3a8a` | white |
| `125 ≤ X < 150`   | `#2563eb` | white |
| `150 ≤ X < 175`   | `#3b82f6` | white |
| `175 ≤ X < 200`   | `#60a5fa` | black |
| `200 ≤ X < 250`   | `#93c5fd` | black |
| `250 ≤ X < 300`   | `#bfdbfe` | black |
| `X ≥ 300`         | `#dbeafe` | black |

The palette is shared with any future skill that displays stock prices.

## Files (5 + modes/__init__.py)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES=["ddm-acoes"]`. |
| `_registry.py`                    | `MODES` + `register_mode` (thin delegate to `skills._base`; Phase 4 C3 removed the pre-merge standalone fallback).  |
| `helpers.py`                      | `format_brl`, `format_int` (PT-BR thousands),          |
|                                   | `format_pct` (signed PT-BR %), `format_value`,          |
|                                   | `_format_mes_ano`, `_format_data`,                      |
|                                   | `distribution_snapshots` ([v2] the shared bucketing).   |
| `report.py`                       | `build_kpi_card`, `build_stocks_table` (sortable +     |
|                                   | `data-value` cells + `sort_types`),                    |
|                                   | `build_distribution_chart` (Chart.js bar with 22       |
|                                   | colored bars from `skills/_colors/price`),             |
|                                   | `build_evolution_sections` ([v2] the 2 stacked-area    |
|                                   | charts), `build_history_note_section`,                  |
|                                   | `build_error_section`.                                 |
| `modes/dashboard.py`              | The 1-tab dashboard (single mode).                     |
| `modes/__init__.py`               | Modes package marker (for auto_discover).              |

## WebUI

The Mercado page's **Ações family** (WebUI v1.17,
`/webui/mercado`) reorganizes this dashboard: Visão Geral (KPIs +
distribution + top-10 + the full sortable table) and Evolução (the
distribution-over-time charts + the per-date table). Same data layer
(`acoes.db` via this query engine — read-only).

## See also

- [`ddm/acoes/CHANGELOG.md`](ddm/acoes/CHANGELOG.md) — version history.
- [`ddm/acoes/ROADMAP.md`](ddm/acoes/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/DDM.md`](../../data_sources/ddm/DDM.md) —
  DDM data source landing page (covers all sub-domains).
