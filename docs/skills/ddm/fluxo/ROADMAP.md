# DDM Fluxo Skill — Roadmap

## v1.0 (current)

- 5-tab dashboard: 1 Fluxo (group: Fluxo, chart + sortable table) +
  4 per-investor tabs (group: Investidores, each with 3 subtabs:
  Diario / Mensal / Anual).
- 5 top-level KPIs: Última data + Total per investor (4 cards).
- Sortable fluxo table (6 columns × ~247 rows, default sort Data DESC).
- Sortable investor tables (2 columns, default sort Data DESC).
- `negative_red=True` on both tables (outflows in red).
- 4-dataset daily bar chart in Fluxo tab (blue / red / amber / green)
  + range selector.
- Per-investor daily bar chart with per-bar green/red colors +
  range selector.
- Monthly cumulative line chart (green/red per-point colors).
- Annual running cumulative line chart (green line) + range selector.
- Values parsed to REAL (floats in millions R$) at the fetcher boundary.
- Sync guard via `REQUIRED_SOURCES = ["ddm-fluxo"]`.
- Freshness tracking via `skills/_freshness.get_freshness()["ddm-fluxo"]`.
- CloudFront bypass via full Chrome 127 browser headers in fetcher.

## Backlog

### P1 — Per-investor comparison overlay

Add a "Comparativo" tab (group: Análise) that overlays all 4 investors'
daily flow as a multi-line chart (one line per investor). The Fluxo
chart already shows 4 bar datasets, but a line overlay would make it
easier to see correlation / divergence between investor types.

### P2 — Foreign-vs-domestic net flow chart

Add a derived chart that nets Estrangeiro (foreign) against the sum of
Institucional + Pessoa física + Inst. Financeira + Outros (domestic).
This single-line chart makes it visually obvious when foreign and
domestic investors are on opposite sides of the market.

### P3 — Volume (abs flow) chart

Add a "Volume" subtab to each investor tab showing the absolute value
(|flow|) of daily trades (regardless of sign). Useful for identifying
high-activity days. Bar chart, single color (e.g. gray).

### P4 — Year-over-year comparison

Add a "YoY" subtab to each investor tab comparing monthly cumulative
flow across multiple years (e.g. Jan-Aug 2026 vs Jan-Aug 2025). Multi-
line chart, one line per year. Requires the DB to have >1 year of data
(currently ~1 year, so this depends on sync cadence).

### P5 — CSV export

Add an "Exportar CSV" button to each table that downloads the current
(possibly filtered + sorted) rows as a CSV file. Pure client-side JS,
no backend change.

### P6 — Calendar heatmap

Add a calendar heatmap (GitHub-style) showing daily flow magnitude for
ONE investor. Each cell = one day, colored green (positive) / red
(negative), intensity = absolute flow. Gives a single-glance overview
of the year's flow pattern.

### P7 — Real-time sync hook

Wire `data_sources/ddm/fluxo/sync_engine.py` into a periodic sync
scheduler so the dashboard always shows the latest trading day's flow
without requiring the user to run `sync_all` manually. Fluxo is
published daily (after market close BRT) — an end-of-day sync cadence
would keep the data fresh.

### P8 — B3 official API integration

Replace the HTML scraper with the official B3 "Estrutura de Negociação"
API (which exposes the same investor-flow data as structured JSON).
This would make the fetcher more resilient to DDM page layout changes
and reduce the CloudFront bypass surface.

### P9 — Investor-type drill-down

For "Institucional", add a subtab showing the breakdown by sub-type
(fundos de pensão, seguradoras, etc.). The /fluxo page does not expose
this — would need a secondary source (B3's Investor Structure report).

## Out of scope

- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Storing PT-BR strings verbatim (like ddm/focus) — the fluxo page has
  a single unit, so parsing to REAL is cleaner and enables SQL
  aggregations (monthly_cumulative, annual_cumulative) without re-parsing.
- Per-stock flow drill-down — the /fluxo page is aggregate (all B3
  stocks). Per-stock flow data would need a separate source (B3
  COTAHIST + investor classification).
- "Outros" as a per-investor tab — Outros is a residual category
  (everything not in the 4 main types). The Fluxo table shows it, but
  a dedicated tab would be misleading since it's not a single
  investor type.
