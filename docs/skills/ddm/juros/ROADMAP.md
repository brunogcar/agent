# DDM Juros Skill — Roadmap

## v1.0 (current)

- 3 juros indices (Selic, Meta Selic, CDI).
- 4-tab dashboard with subtabs (Histórico + Matriz) per index.
- 3-dataset Histórico chart (month_value + media_no_ano + media_12m).
- Matriz heatmap (red→white→green diverging on all 12 month columns).
- Overlay chart for Comparativo tab (month_value for all 3 indices).

## Backlog

### P1 — More juros indices

Add to `JUROS_CATALOG` once DDM pages are confirmed stable:

- `taxa-juros-tjlp` — TJLP (Taxa de Juros de Longo Prazo).
- `taxa-juros-tr` — TR (Taxa Referencial).
- `taxa-juros-tlp` — TLP (Taxa de Longo Prazo, substitutes TJLP for
  some housing loans).

Each addition is ~5 lines in `catalog.py` + 1 line in
`modes/dashboard.py._INDEX_SLUGS` + a new color entry in `report.INDEX_COLORS`.
No schema changes required (PK is `slug` so any new slug is automatically
supported).

### P2 — Forward-rate overlay

Once `bcb/focus` (analyst expectations) is wired into a Future-juros view,
overlay the Focus median forecast for the Selic 12-month-forward on the
Histórico chart so users can see market expectations vs. realized values.

### P3 — Volatility bands

Add shaded ±1σ bands around the `media_12m` line based on the rolling
12-month standard deviation. Highlights regime shifts (e.g. 2020 COVID
volatility spike).

### P4 — Real interest rate

Add a derived "juros reais" column = `month_value - ipca_acumulado_12m`
(Selic deflated by IPCA). Requires a cross-domain join with
`ddm/inflation` data. Useful for showing whether the policy rate is
positive or negative in real terms.

### P5 — Comparativo enhancements

- Toggle to switch between `month_value`, `media_no_ano`, and `media_12m`
  in the Comparativo overlay (currently hard-coded to `month_value`).
- Range selector that already exists; add a "YTD only" toggle for
  comparing just the year-to-date averages across all 3 indices.

### P6 — Sub-domain expansion: `ddm/stocks`

Equity snapshots / price history from DDM. Mirror the juros layout
(`__init__.py` + `catalog.py` + `fetcher.py` + `sync_engine.py` +
`query_engine.py` + `status_reporter.py`) into `data_sources/ddm/stocks/`
with `memory_db/ddm/stocks/stocks.db`. Auto-discovery picks it up
automatically — no changes to `data_sources/ddm/__init__.py` needed.

### P7 — Real-time sync hook

Wire `data_sources/ddm/__init__.py` into a periodic sync scheduler so
the dashboard always shows fresh data without requiring the user to run
`sync_all` manually. Likely a cron entry on the agent host. Selic/CDI
rates change daily (Mon-Fri business days) so a daily sync is sufficient.

### P8 — ETag / Last-Modified caching

DDM pages are static HTML; the server may return `ETag` or
`Last-Modified` headers. Use them to skip re-fetching when the page
hasn't changed (saves bandwidth + parse time on auto-syncs).

### P9 — Subtab URL deep-linking

Add subtab anchors to the URL hash so users can deep-link to e.g.
`?tab=cdi&subtab=matriz`. Currently subtabs are local-state only.

## Out of scope

- Building a `ddm/stocks` or `ddm/funds` skill dashboard until the
  underlying data sources exist (P6).
- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Computing daily (not monthly) juros series — the DDM pages ship only
  monthly aggregates. For true daily rates, use `bcb/sgs` (codes 11 + 12).
