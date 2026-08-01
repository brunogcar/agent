<- Back to [Historical Overview](../HISTORICAL.md)

# 🗺️ Historical ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | H1 — Trend line charts | Line chart per metric showing 5Y time series |
| P3 | H2 — More metrics | Add leverage, efficiency, growth to dashboard |
| P3 | H3 — Export to xlsx | Export percentile + trend tables to Excel |
| Done | v2.1 dashboard reorg | 3→5 tabs: subtabs by category, F7 speed fix, charts, ratio_grid |
| Done | Sync guard (v2.1) | required_sources wired via make_route() |
| Done | F7 engine cache (v1.9) | Inherited from calculations skill |
| Done | Subtabs by category (v2.1) | Valuation / Profitability subtab split |
| Done | More metrics (v2.1) | Added Marg. Bruta + Marg. Líquida |

---

## ✅ Recently Completed

- **v2.1 (2026-07-31)** — Dashboard reorg: 3→5 tabs (Overview / Valuation
  subtabs / Profitability subtabs / Ratio Grid / Percentile Analysis). F7
  speed fix: wrapped all summary() + fetch_quartiles() in engine_cache_scope.
  Added 2 metrics (Marg. Bruta + Marg. Líquida). Detailed [historical] output.
  Sync guard wired. 8 tests.

---

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

*Last updated: 2026-07-31 (v2.0 — dashboard reorg + sync guard). See [CHANGELOG.md](CHANGELOG.md) for version history.*
