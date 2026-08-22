# DDM Dividends Skill — Roadmap

## v1.0 (current)

- 1-tab dashboard (Dividendos).
- 4 KPI cards at top level.
- Grouped bar distribution chart (Dividendo vs JCP, 8 value-range buckets).
- Sortable dividends table (default sort: Valor DESC; click headers to
  re-sort).
- Dates displayed as DD/MM/YYYY (PT-BR).
- Sync guard wired (`REQUIRED_SOURCES = ["ddm-dividends"]`).
- Freshness tracking wired (`skills/_freshness.py` reads `sync_state`).

## Backlog

### P1 — Filter by date range

Add query params to `dividends_list` for filtering by record_date /
ex_date / payment_date range (e.g. `record_date_from=2026-01-01`,
`record_date_to=2026-12-31`). Useful for "show me all dividends declared
in Q3 2026".

### P2 — Per-ticker dividend history tab

When the user passes `ticker=PETR4`, add a second tab showing the full
dividend history for that ticker (line chart of value over time +
sortable table). Reuses `query_engine.ticker_history`.

### P3 — Dividend yield calculation

Cross-reference dividend values with stock prices from `b3/price` to
compute dividend yield (value / current_price). Requires a join with
`b3/cotahist` or `b3/brapi` data. Useful for income-investor screening.

### P4 — Ex-dividend date calendar view

A monthly calendar visualization showing which tickers go ex-dividend
each day. Currently the dashboard shows a flat table — a calendar view
would highlight clusters of activity (e.g. Q1 is heavy on bank
dividends, Q2 on commodities).

### P5 — Dividendo vs JCP split chart

Add a doughnut chart showing the count split between Dividendo and JCP
(currently only shown in the KPI subtitle). Quick visual of the tax
strategy distribution.

### P6 — Cumulative dividend income (per ticker)

For a given ticker + a starting date, plot the cumulative dividend
income received per share. Useful for long-term holders tracking total
return contributions from dividends vs price appreciation.

### P7 — Auto-sync schedule

Wire the dividends sync into a periodic scheduler (e.g. daily at market
close). The agenda page updates as companies announce dividends, so a
daily sync keeps the dashboard current without manual `sync_all` calls.

### P8 — Sort by ISO date under the hood

Currently the sortable table marks date columns as `sort_type="text"`,
which means the `sortTable()` JS uses `textContent` (DD/MM/YYYY) for
sorting. This sorts incorrectly lexicographically ("01/07" < "10/07" <
"02/07" — wrong order). Fix: emit `data-value="2026-07-01"` (ISO format)
on date cells + update the sortTable JS to use `data-value` for text
columns too when present. Out of scope for v1 (the default sort is
Valor DESC, which works correctly).

### P9 — Pagination for large result sets

If the agenda grows beyond ~500 rows, the table will become unwieldy.
Add client-side pagination (50 rows per page) or virtualized scrolling.

## Out of scope

- Building a `ddm/stocks` or `ddm/funds` skill dashboard until the
  underlying data sources exist.
- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Computing per-share dividend history for delisted tickers — DDM only
  publishes upcoming events, not historical dividends. Use `b3/dividends`
  for historical events.
