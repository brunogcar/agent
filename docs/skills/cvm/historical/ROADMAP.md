<- Back to [Historical Overview](../HISTORICAL.md)

# 🗺️ Historical ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| Done | H1 — Trend line charts | Done (already had `build_trend_line_chart`, now applied to all metric categories in v1.16) |
| Done | H2 — More metrics | Done (leverage/efficiency/growth added v1.16 — debt_equity, net_debt_ebitda, interest_coverage, asset_turnover, inventory_turnover, revenue_growth_3m, net_income_growth_3m) |
| P3 | H3 — Export to xlsx | Export percentile + trend tables to Excel |
| Done | H4 — Beta (5Y) | Done (built in calculations v1.13, not historical — 5Y rolling OLS regression vs IBOV fits the engine registry pattern there) |
| Done | H5 — BCB SGS macro indicators | Done (BCB SGS built v1.0 — Selic via series 11 already wired into calculations `selic` engine + COE metric in v1.13) |
| Done | v1.14 dashboard reorg | 3→5 tabs: subtabs by category, F7 speed fix, charts, ratio_grid |
| Done | v1.16 dashboard expansion | 5→7 tabs: added Liquidez e Alavancagem + Eficiência e Crescimento tabs with subtabs + per-metric 5Y charts |
| Done | Sync guard (v1.14) | required_sources wired via make_route() |
| Done | F7 engine cache (v1.9) | Inherited from calculations skill |
| Done | Subtabs by category (v1.14) | Valuation / Profitability subtab split |
| Done | More metrics (v1.14) | Added Marg. Bruta + Marg. Líquida |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### H1 — Trend line charts

**Priority:** P2

Add a line chart to the Trend tab showing each metric's 5Y time series.
Currently the Trend tab is a table only. A line chart would visualize
whether the metric is trending up/down/sideways.

**Blocker:** Requires fetching the full series data per metric (currently
only summary() is called, which doesn't expose the full series to the
dashboard). Could call `spec.history_fn()` directly or enhance summary()
to include the series.

### H2 — Subtabs by metric category

**Priority:** P2

Split the dashboard into subtabs by metric category:
- Valuation (P/L, P/VPA, EV/EBITDA)
- Profitability (ROE, ROIC, Div Yield)

The template supports `type: "subtabs"` already. Would require restructuring
the tab sections into a subtabs section.

### H3 — More metrics

**Priority:** P3

Add more metrics to the dashboard beyond the current 6:
- Margins (gross, operating, net, EBITDA)
- Leverage (D/E, net debt/EBITDA)
- Efficiency (asset turnover, inventory turnover)
- Growth (revenue growth 1Y/5Y)

Would require expanding `_METRIC_DEFS` + the mock in tests.

### H4 — Export to xlsx

**Priority:** P3

Export the percentile + trend tables to Excel via the report tool's
xlsx adapter. Would need a `historical_dashboard` adapter that maps
each tab to a sheet.

---

*Last updated: 2026-08-05. See [CHANGELOG.md](CHANGELOG.md) for version history.*
