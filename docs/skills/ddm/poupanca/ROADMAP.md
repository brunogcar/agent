# DDM Poupanca Skill — Roadmap

## v1.0 (current)

- 1 poupanca index (Poupanca).
- 1-tab dashboard with subtabs (Histórico + Matriz).
- 3-dataset Histórico chart (month_value + acumulado_no_ano + acumulado_12m,
  using SUM not AVERAGE).
- Matriz heatmap (red→white→green diverging on all 12 month columns,
  with `{text, bg, color}` cell dicts).
- `negative_red=True` on the Histórico table (poupanca yields can be
  negative during high-inflation periods).
- Section titles without the index-name prefix (cleaner headers).

## Backlog

### P1 — Real interest rate (juros reais) on poupanca

Add a derived "rendimento real" column = `month_value - ipca_acumulado_12m`
(poupanca monthly yield deflated by IPCA). Requires a cross-domain join
with `ddm/inflation` data. Useful for showing whether poupanca is positive
or negative in real terms.

### P2 — Comparativo tab (only if a second index is added)

Currently poupanca has only 1 index in the catalog. If a second index is
added to `POUPANCA_CATALOG` (e.g. a different savings product), add a
Comparativo tab following the `ddm/juros` pattern (overlay chart of
`month_value` for all indices, last 24 months, NO tables).

### P3 — Volatility bands

Add shaded ±1σ bands around the `acumulado_12m` line based on the rolling
12-month standard deviation. Highlights regime shifts (e.g. 2015-2016
high-inflation period when poupanca yields spiked).

### P4 — Year-end summary card

Add a top-level "Resumo Anual" card showing the year-end `acumulado_no_ano`
for the last 5 years. Poupanca is a long-term savings product, so the
annual cumulative return is the most-watched metric.

### P5 — Tax-adjusted yield

Brazilian poupanca has tax implications (IR on yields if withdrawn before
the minimum holding period). Add an optional toggle to show the
post-tax yield based on the user's tax bracket. Likely requires a
`tax_bracket` parameter to the dashboard mode.

### P6 — Sub-domain expansion: `ddm/stocks` or `ddm/funds`

Equity snapshots / fund quotes from DDM. Mirror the poupanca layout
(`__init__.py` + `catalog.py` + `fetcher.py` + `sync_engine.py` +
`query_engine.py` + `status_reporter.py`) into `data_sources/ddm/stocks/`
or `data_sources/ddm/funds/` with `memory_db/ddm/stocks/stocks.db`.
Auto-discovery picks it up automatically — no changes to
`data_sources/ddm/__init__.py` needed.

### P7 — Real-time sync hook

Wire `data_sources/ddm/__init__.py` into a periodic sync scheduler so
the dashboard always shows fresh data without requiring the user to run
`sync_all` manually. Likely a cron entry on the agent host. Poupanca
yields change monthly (BCB publishes the monthly rate in the first week
of the following month) so a weekly sync is sufficient.

### P8 — ETag / Last-Modified caching

DDM pages are static HTML; the server may return `ETag` or
`Last-Modified` headers. Use them to skip re-fetching when the page
hasn't changed (saves bandwidth + parse time on auto-syncs).

### P9 — Subtab URL deep-linking

Add subtab anchors to the URL hash so users can deep-link to e.g.
`?tab=poupanca&subtab=matriz`. Currently subtabs are local-state only.

## Out of scope

- Building a `ddm/stocks` or `ddm/funds` skill dashboard until the
  underlying data sources exist (P6).
- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Computing daily (not monthly) poupanca yields — the DDM pages ship
  only monthly aggregates. For true daily rates, use `bcb/sgs`.
- A Comparativo tab in v1 — poupanca has only 1 index, so there's
  nothing to overlay (P2 would add one only if a second index joins the
  catalog).
