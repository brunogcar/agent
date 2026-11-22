# DDM Proventos Skill — Roadmap

## v2 (current — WebUI v1.18)

- 4-tab dashboard: Proventos (B3 natives), BDRs, Por Empresa, Calendário.
- BDR split on `is_bdr(ticker)` (the *34 predicate) in every view.
- 6 top-level KPIs (whole agenda) + per-scope KPIs in the WebUI subtabs.
- Grouped bar distribution (Dividendo vs JCP, 8 buckets) + tipo doughnut.
- Per-empresa aggregation (Top 10 charts + full table, B3/BDR colored).
- Per-day calendar (Pago vs A pagar + per-day table with top-3 payers).
- Shared numerics in `helpers.py` (used by the static AND the WebUI
  Proventos family — no forked numerics).
- Sortable tables (Valor DESC default; dates DD/MM/YYYY PT-BR).
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
columns too when present. Out of scope for v2 (the default sorts are
Valor/Valor Total/Data DESC — the WebUI tables sort dates correctly via
_valSortKey; only the STATIC is affected).

### P9 — Pagination for large result sets

If the agenda grows beyond ~500 rows, the table will become unwieldy.
Add client-side pagination (50 rows per page) or virtualized scrolling.

### P10 — BDR origin metadata

DDM only exposes the ticker + company name; a `bdr_origin` mapping
(underlying foreign ticker + exchange) would enrich the BDRs tab. Needs
an additional source (B3 BDR list) — out of scope until that source
exists in the repo.

## Shipped (from the v1 backlog)

- ~~P4 — Ex-dividend date calendar view~~ → the v2 **Calendário** tab
  (per-day payments chart + table; a month-grid view remains possible
  as a future polish).
- ~~P5 — Dividendo vs JCP split chart~~ → the v2 **tipo doughnut** in
  the Proventos tab.

## Out of scope

- Building a `ddm/stocks` or `ddm/funds` skill dashboard until the
  underlying data sources exist.
- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Computing per-share dividend history for delisted tickers — DDM only
  publishes upcoming events, not historical dividends. Use `b3/dividends`
  for historical events.
