<- Back to [B3 Skills](../B3.md)

# 📈 PRICE — B3 Price Analytics Skill

The `price` skill produces a 5-tab price dashboard for any B3-listed equity:
candlestick + moving averages + volume + returns + volatility (Bollinger Bands).

**Key characteristics:**
- **Two modes** — `dashboard` (5-tab deep dive) + `quote` (latest OHLCV snapshot).
- **Single data source** — `data_sources/b3/cotahist` (daily OHLCV from B3 official
  COTAHIST ZIP files). No CVM cross-domain joins, no investsite. Pure price action.
- **10-year window** — fetches up to 10 years of history so the range selector
  (Tudo/10A/5A/1A/6M/3M/1M) has data to filter.
- **Candlestick support** — the Cotação tab's OHLC candles are rendered by the
  vanilla `_renderOHLCChart` helper (flagged via `chart_data._ohlc = True`),
  not the `chartjs-chart-financial` plugin (removed in v1.1). The helper lives
  in `templates/js/dashboard_charts.html` (included by `dashboard.html`).
- **Computational engines** — `engines.py` is the single home for all math:
  SMA, returns, drawdowns, rolling volatility, Bollinger Bands, MA crossovers,
  52-week range. Report builders in `report/` are pure shape — they consume
  engine output and emit section dicts. NO computation in builders.
- **Sync guard** — `REQUIRED_SOURCES = ["cotahist"]` + `make_route()` ensures
  the cotahist DB is fresh (24h window) before each dispatch.

---

## 🚀 Quick Start

```
# 5-tab dashboard (candlestick + MA + volume + returns + volatility)
skill(domain="b3", sub_domain="price", mode="dashboard", params='{"ticker":"PETR4"}')

# Latest quote + 52-week range (compact KPI list, no charts)
skill(domain="b3", sub_domain="price", mode="quote",     params='{"ticker":"PETR4"}')
```

Every `route(mode="dashboard", ...)` call auto-generates an HTML file
(`PETR4_price_dashboard.html` in `workspace/reports/`).

---

## ⚙️ Configuration

Read-only over already-synced data sources:
- `data_sources/b3/cotahist` (cotahist.db — daily OHLCV since 2010)

Sync command (run once before first use):
```powershell
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2024))"
```

Escape hatches (set automatically in tests):
- `CVM_SKIP_SYNC=1` — bypass sync guard (no freshness check, no force-sync)
- `CVM_SKIP_HTML=1` — skip auto-HTML generation

---

## 📊 Rendering & Export

Pipe a `price` result into the `report` tool to render a table or export to
Excel. The `dashboard` action auto-writes HTML — see [B3 Skills — Auto-HTML
Generation](../B3.md#-auto-html-generation).

The dashboard template (`tools/report_ops/templates/dashboard.html`) loads one
Chart.js library:
1. **chart.js 4.4.1** — line, bar, doughnut, area charts. The candlestick chart
   in the Cotação tab is rendered by the vanilla `_renderOHLCChart` helper
   (flagged via `chart_data._ohlc = True`), NOT the `chartjs-chart-financial`
   plugin (removed in v1.1).

The chart-rendering JS (`_renderChart`, `filterPriceChart`, `_applySegmentColors`,
`_renderOHLCChart`, `togglePeriod`, `toggleChartCollapsible`, the
`priceDatalabels` Chart.js plugin, and the theme-toggle re-render override)
lives in `templates/js/dashboard_charts.html` + `templates/js/dashboard_theme_override.html`,
wired into `dashboard.html` via Jinja2 `{% include %}` (Phase 3 C3 extraction —
was inline in dashboard.html).

The range selector (Tudo/10A/5A/1A/6M/3M/1M) is rendered by `macros.html`'s
`_section_inner()` macro and filtered client-side by `filterPriceChart()` JS.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](price/ARCHITECTURE.md) | File map, data flow, engine design, candlestick chart shape |
| [API.md](price/API.md) | 2 modes (dashboard, quote) + params + response shapes |
| [CHANGELOG.md](price/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](price/INSTRUCTIONS.md) | AI editing rules — what NOT to break, ALWAYS DO |
| [ROADMAP.md](price/ROADMAP.md) | Backlog: RSI, MACD, intraday, options, dividend-adjusted returns |

---

*Last updated: 2026-08-06 (v1.0 — price skill launch).*
