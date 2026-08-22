# DDM Focus Skill

Skill: **`ddm/focus`**
Mode: `dashboard` (13 tabs)
Data source: `data_sources/ddm/focus/` (read-only queries against
`memory_db/ddm/focus.db`).

## Overview

A 13-tab dashboard for the Brazilian Boletim Focus (market expectations
survey) scraped from dadosdemercado.com.br/boletim-focus:

1. **Focus** — 4 year subtabs (2026, 2027, 2028, 2029), each showing
   all 12 indicators for that year.
2. **IPCA** — chart + 3 time-window subtabs.
3. **PIB Total** — same.
4. **Câmbio** — same.
5. **Selic** — same.
6. **IGP-M** — same.
7. **IPCA Adm** — same.
8. **Conta corrente** — same.
9. **Balança comercial** — same.
10. **Investimento direto no país** — same.
11. **Dívida líquida setor pub** — same.
12. **Resultado primário** — same.
13. **Resultado nominal** — same.

### Focus tab (group: Boletim)

The Focus tab has 4 subtabs, one per target year (2026-2029). Each
subtab shows a sortable year table with 12 indicator rows and 6 columns:

| Indicador | Há 4 semanas | 1 sem | Hoje | Comp. | Resp. |

- `sortable=True` + `default_sort = {"column": 0, "direction": "asc"}`
  (Indicador ASC).
- `sort_types = ["text","text","text","text","text","number"]`.
- Value cells carry `data-value` attributes (parsed float) for accurate
  numeric sorting.
- Comp. column cells are colored glyphs: ▲ green, ▼ red, = gray.

### Indicator tabs (group: Indicadores)

Each indicator tab has:

- **A grouped bar chart** at the top showing 3 datasets (Há 4 semanas /
  1 sem / Hoje) × 4 years (2026-2029). Colors: teal (4 semanas),
  amber (1 sem), blue (hoje). The chart makes it easy to see how
  expectations for this indicator evolved across years and how they
  shifted over the past 4 weeks.
- **3 subtabs** (Há 4 semanas / 1 sem / Hoje), each showing a sortable
  per-year table:

| Ano | Há 4 semanas | 1 sem | Hoje | Comp. | Resp. |

  - `sortable=True` + `default_sort = {"column": 0, "direction": "asc"}`
    (Ano ASC).
  - `sort_types = ["number","text","text","text","text","number"]`.

### KPIs (top-level, 4 cards)

| KPI                    | Source                  | Example             |
| ---------------------- | ----------------------- | ------------------- |
| Data de referência     | `all_data().ref_date`   | `2025-01-15`        |
| Anos cobertos          | `summary().year_count`  | `4` (2026-2029)     |
| Indicadores            | `summary().indicator_count` | `12`             |
| Total de observações   | `summary().row_count`   | `48` (4 years × 12) |

## Why values are stored as strings

Unlike the other DDM sub-domains (`acoes`, `inflation`, `juros`,
`poupanca`) which normalize PT-BR numbers to floats at the fetcher
boundary, the Focus subdomain preserves the value strings verbatim
(`"5,151%"`, `"R$ 5,200"`). This is because:

1. The Focus page mixes percentage, currency, and integer-count columns
   in the same snapshot, so a single normalization would lose type info.
2. The user wants to see exactly what the source shows — no rounding,
   no PT-BR → EN conversion.
3. The chart builder parses the strings to floats on demand (via
   `parse_numeric`) so the chart still works.

The `respondents` column is the exception: it's always a plain integer
count, so it's stored as INTEGER for accurate sorting.

## Usage

```python
from skills.ddm.focus import route as focus_skill

# Full dashboard (auto-syncs ddm-focus source if stale).
focus_skill(mode="dashboard")

# Skip sync guard (e.g. for quick reads against a known-fresh DB).
focus_skill(mode="dashboard", skip_sync=True)
```

Or via the skill dispatcher:

```
skill(domain="ddm", sub_domain="focus", mode="dashboard")
```

## Chart colors

The 3 time-window datasets use a fixed palette:

| Dataset          | Color  | Hex       |
| ---------------- | ------ | --------- |
| Há 4 semanas     | teal   | `#14b8a6` |
| 1 sem            | amber  | `#f59e0b` |
| Hoje             | blue   | `#3b82f6` |

The Comp. column uses:

| Comparison | Glyph | Color     | Hex       |
| ---------- | ----- | --------- | --------- |
| up         | ▲     | green     | `#22c55e` |
| down       | ▼     | red       | `#ef4444` |
| flat       | =     | gray      | `#9ca3af` |

## Sync guard

`REQUIRED_SOURCES = ["ddm-focus"]` — the route wrapper checks the
freshness of the `ddm-focus` source before each dispatch and triggers
a force-sync if stale (>24h or missing).

`skills/_base._trigger_sync.sync_map["ddm-focus"]` calls
`data_sources.ddm.focus.sync_engine.sync_all(force=True)` — re-fetches
the `/boletim-focus` page (with full Chrome 127 browser headers to
bypass CloudFront) and `INSERT OR REPLACE`s all rows.

`skills/_freshness.get_freshness()` includes a `ddm-focus` key so any
consumer can poll the last-sync timestamp for the focus DB.

Tests bypass via `CVM_SKIP_SYNC=1` or `skip_sync=True` per-call.

## Files (5 + modes/__init__.py)

| File                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `__init__.py`                     | MANIFEST + `route()` + `REQUIRED_SOURCES=["ddm-focus"]`. |
| `_registry.py`                    | `MODES` + `register_mode` (with standalone fallback).  |
| `helpers.py`                      | `format_value` (verbatim), `format_int` (PT-BR         |
|                                   | thousands), `comparison_symbol`, `comparison_color`,   |
|                                   | `parse_numeric` (PT-BR string -> float for charts).    |
| `report.py`                       | `build_kpi_card`, `build_year_table` (sortable +       |
|                                   | `data-value` cells + colored Comp. cells),             |
|                                   | `build_indicator_table` (sortable + Ano number sort),  |
|                                   | `build_indicator_chart` (grouped bar, 3 datasets),     |
|                                   | `build_error_section`.                                 |
| `modes/dashboard.py`              | The 13-tab dashboard (single mode).                    |
| `modes/__init__.py`               | Modes package marker (for auto_discover).              |

## See also

- [`ddm/focus/CHANGELOG.md`](ddm/focus/CHANGELOG.md) — version history.
- [`ddm/focus/ROADMAP.md`](ddm/focus/ROADMAP.md) — backlog.
- [`../../data_sources/ddm/focus/API.md`](../../data_sources/ddm/focus/API.md)
  — underlying data source API.
- [`../../data_sources/ddm/DDM.md`](../../data_sources/ddm/DDM.md) —
  DDM data source landing page (covers all 5 sub-domains).
