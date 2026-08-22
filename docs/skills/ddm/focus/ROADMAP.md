# DDM Focus Skill — Roadmap

## v1.0 (current)

- 13-tab dashboard: 1 Focus (group: Boletim, 4 year subtabs) + 12
  indicator tabs (group: Indicadores, each with chart + 3 time-window
  subtabs).
- 4 top-level KPIs: Data de referência, Anos cobertos, Indicadores,
  Total de observações.
- Sortable year table (12 indicators × 6 columns, default sort
  Indicador ASC).
- Sortable indicator table (4 years × 6 columns, default sort Ano ASC).
- Grouped bar chart per indicator (3 datasets × 4 years, teal/amber/
  blue palette).
- Colored Comp. column (▲ green, ▼ red, = gray).
- Values stored as PT-BR strings verbatim; chart builder parses to
  floats on demand.
- Sync guard via `REQUIRED_SOURCES = ["ddm-focus"]`.
- Freshness tracking via `skills/_freshness.get_freshness()["ddm-focus"]`.
- CloudFront bypass via full Chrome 127 browser headers in fetcher.

## Backlog

### P1 — Historical time-series view

The DB schema preserves historical snapshots (`PRIMARY KEY (year,
indicator, ref_date)`), but the dashboard currently only shows the
latest `ref_date`. Add a "Histórico" subtab to each indicator tab that
shows a line chart of `today` values over the last N syncs (e.g. last
12 weeks). This would let users see how expectations drifted over time.

### P2 — Indicator comparisons

Add a "Comparativo" tab (group: Análise) that overlays the `today`
values for selected indicators across all 4 years. E.g. compare IPCA
vs IGP-M vs IPCA Adm to see which inflation measure the market expects
to run hotter. Multi-line chart, one line per indicator.

### P3 — Per-year comparison chart

Add a chart to each Focus year subtab showing all 12 indicators as a
single grouped bar chart (X-axis = indicators, Y-axis = today value).
This would give a single-glance overview of the year's expectations.
Probably needs a logarithmic Y-axis since IPCA (~5%) and Cambio (~5)
have different units.

### P4 — Cross-year delta column

Add a "Δ 4 sem" column to the year table showing the difference
between `today` and `four_weeks_ago` (parsed to floats). Positive =
expectations rose over the past 4 weeks; negative = expectations fell.
Color the cell green / red based on sign.

### P5 — Sortable indicator tabs by indicator name

Currently the 12 indicator tabs are in a fixed order (IPCA, PIB Total,
Cambio, Selic, ...). Add a small "Reordenar" control that lets users
sort the indicator tabs alphabetically or by today-value-DESC. Pure
client-side JS — no backend change.

### P6 — CSV export

Add an "Exportar CSV" button to each table that downloads the current
(possibly filtered + sorted) rows as a CSV file. Pure client-side JS,
no backend change.

### P7 — Real-time sync hook

Wire `data_sources/ddm/focus/sync_engine.py` into a periodic sync
scheduler so the dashboard always shows the latest bulletin without
requiring the user to run `sync_all` manually. Focus is published
weekly (Friday afternoons BRT) — a daily sync cadence Monday morning
would keep the data fresh.

### P8 — Confidence band chart

For indicators where respondents report a range (not currently captured
on the page — would need to scrape a secondary source), add a band
chart showing the min/median/max expectations over time. Requires
schema extension to capture distributional data.

### P9 — Year-over-year delta subtab

Add a 4th subtab to each indicator tab: "Δ Ano" showing the per-year
delta (e.g. how much higher are 2027 IPCA expectations vs 2026).
Single-bar chart + table.

## Out of scope

- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Storing normalized floats in the DB instead of PT-BR strings —
  would lose the source format and complicate the dashboard rendering.
  The `parse_numeric` helper handles the conversion at chart time only.
- Per-respondent drill-down — the page only shows the count, not the
  individual respondents. Would need a separate data source
  (BCB Olinda OData API for the official Focus survey).
- Adding "data do boletim" column — DDM does not expose it on the page
  (it's an aggregate snapshot). Using `ref_date` (sync date,
  YYYY-MM-DD) as the proxy is the closest approximation.
