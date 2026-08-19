# DDM Inflation Skill — Roadmap

## v1.0 (current)

- 3 inflation indices (IGP-M, IPCA, INPC).
- 4-tab dashboard (per-index + Comparativo).
- Historical monthly series + monthly matrix table per index.
- Overlay chart for Comparativo tab.

## Backlog

### P1 — More inflation indices

Add to `INDEX_CATALOG` once DDM pages are confirmed stable:

- `ipca-15` — IPCA-15 (IBGE, early preview of IPCA).
- `ipc-fiipe` — IPC-FIPE (USP, broader CPI variant).
- `icv-dieese` — ICV (DIEESE, union-tracked cost of living).
- `cpi` — Consumer Price Index (if DDM publishes one).

Each addition is ~5 lines in `catalog.py` + 1 line in
`modes/dashboard.py._INDEX_SLUGS`. No schema changes required (PK is
`slug` so any new slug is automatically supported).

### P2 — Annual acumulado chart

Currently the per-index tabs show monthly variation + 12m acumulado. Add a
3rd dataset for the year acumulado (`year_acumulado`) on a secondary
y-axis so users can see the YTD trajectory alongside monthly pulse.

### P3 — Heatmap matrix

Replace the plain matrix table with a colored heatmap (green = low / red
= high) using the `b3/options` heatmap section builder. Currently the
matrix is just text — a heatmap would surface regime shifts more
visually.

### P4 — Cross-index correlation

Add a new mode `correlation` that computes the rolling 12m correlation
between index pairs (IGP-M ↔ IPCA, IPCA ↔ INPC, etc.) and renders a
heatmap matrix.

### P5 — Forecast overlay

Once a DDM `forecast` sub-domain is built (analyst expectations), overlay
the median forecast on each per-index tab so users can see market
expectations vs. realized values.

### P6 — Sub-domain expansion: `ddm/stocks`

Equity snapshots / price history from DDM. Mirror the inflation layout
(`__init__.py` + `catalog.py` + `fetcher.py` + `sync_engine.py` +
`query_engine.py` + `status_reporter.py`) into
`data_sources/ddm/stocks/` with `memory_db/ddm/stocks/stocks.db`.
Auto-discovery picks it up automatically — no changes to
`data_sources/ddm/__init__.py` needed.

### P7 — Sub-domain expansion: `ddm/funds`

Investment fund quotes / portfolios from DDM. Same shape as P6, with
`memory_db/ddm/funds/funds.db`.

### P8 — Real-time sync hook

Wire `data_sources/ddm/__init__.py` into a periodic sync scheduler so
the dashboard always shows fresh data without requiring the user to run
`sync_all` manually. Likely a cron entry on the agent host.

### P9 — ETag / Last-Modified caching

DDM pages are static HTML; the server may return `ETag` or
`Last-Modified` headers. Use them to skip re-fetching when the page
hasn't changed (saves bandwidth + parse time on auto-syncs).

## Out of scope

- Building a `ddm/stocks` or `ddm/funds` skill dashboard until the
  underlying data sources exist (P6/P7).
- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
