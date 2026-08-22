# DDM Acoes Skill — Roadmap

## v1.0 (current)

- 1-tab dashboard (Ações) with no subtabs.
- 4 top-level KPIs: Total de Ações, Mais Negociada, Maior Alta, Maior Baixa.
- Sortable stocks table (5 columns, default sort: Negócios DESC).
- Price-distribution chart (16 colored bars from `skills/_price_colors`).
- Sortable-table feature added to `macros.html` + `base.html` (reusable
  by future skills).
- Shared `skills/_price_colors.py` module (16-range palette).
- Sync guard via `REQUIRED_SOURCES = ["ddm-acoes"]`.
- Freshness tracking via `skills/_freshness.get_freshness()["ddm-acoes"]`.

## Backlog

### P1 — Per-ticker detail subtab

Add a subtab to the Ações tab that shows a single ticker's snapshot in
more detail (last price, variation, negócios, ref_date) + a link to the
DDM page (`/acoes/{slug}`). Probably triggered by clicking a row in the
stocks table (would need a small JS hook to set the active ticker).

### P2 — Filter / search box

Add a text-input filter above the stocks table that filters rows in
real-time by ticker or name. The `search` query mode exists in the data
source; the dashboard would just need a JS-side filter (no extra HTTP
call) for snappy UX. Probably 10-20 lines of vanilla JS in `base.html`.

### P3 — Sector / industry grouping

DDM doesn't expose sector on the `/acoes` page, but `data_sources/cvm/cad`
(company register) has it. Join on ticker → add a "Setor" column or a
sector-grouped view. Requires a cross-domain join with the CVM bridge.

### P4 — Intraday vs historical toggle

The acoes page is a single snapshot. Adding a "Histórico" subtab that
shows the last N syncs of a ticker (line chart of `last_price` over
sync timestamps) would let users see short-term trends. Requires either
appending to a `stocks_history` table on each sync, or joining with
`data_sources/b3/cotahist` for the official daily close.

### P5 — Custom price-range palette per skill

Currently all skills share the same 16-range palette from
`skills/_price_colors`. Some skills (e.g. a future small-caps-only view)
might want a tighter palette (e.g. only sub-R$20 ranges). Add a
`price_distribution(prices, ranges=None)` parameter that lets the caller
override the default `_RANGES` list.

### P6 — Sortable-table feature adoption

Now that the sortable-table feature exists in `macros.html`, other
dashboards with large tables (e.g. `cvm/screener`, `cvm/comparison`,
`b3/options` Cadeia de Opções) could adopt it. Each adoption is a small
change to the relevant `report.py` (add `sortable=True` +
`default_sort` + `sort_types` to the section dict).

### P7 — Distribution chart legend

The price-distribution chart currently has no legend (the bar colors
are self-documenting via the X-axis labels). A small legend strip
above the chart (showing each range's color swatch + label) would help
colorblind users. Probably a small HTML table rendered alongside the
chart canvas.

### P8 — Real-time sync hook

Wire `data_sources/ddm/acoes/sync_engine.py` into a periodic sync
scheduler so the dashboard always shows fresh prices without requiring
the user to run `sync_all` manually. B3 trading hours are 10:00-17:30
BRT on weekdays — a 15-minute sync cadence during trading hours would
keep prices within ~15 min of real-time.

### P9 — CSV export

Add a "Exportar CSV" button to the stocks table that downloads the
current (possibly filtered + sorted) rows as a CSV file. Pure client-
side JS, no backend change.

## Out of scope

- Replacing the regex parser with BeautifulSoup — the site is stable
  and regex is sufficient; the extra dependency is not justified.
- Computing technical indicators (RSI, MACD, moving averages) on the
  acoes snapshot — those need historical data, not a single snapshot.
  Use `b3/price` skill for technical analysis (it reads `cotahist.db`
  which has full daily history).
- A "Comparativo" tab — there's only one acoes page, so there's nothing
  to overlay (unlike `ddm/juros` which has 3 indices to compare).
- Storing historical snapshots in `acoes.db` — the schema is intentionally
  flat (one row per ticker, refreshed on each sync). Historical price
  data is `cotahist`'s job.
