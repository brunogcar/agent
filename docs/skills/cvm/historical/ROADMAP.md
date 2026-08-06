<- Back to [Historical Overview](../HISTORICAL.md)

# 🗺️ Historical ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P1 | H6 — WACC + DCF intrinsic value | COE × E/(D+E) + after-tax Kd × D/(D+E) → discount FCFF → per-share intrinsic value vs current price. Reuses coe_at + debt + ebit + capex + tax + shares + price. |
| P1 | H7 — Sector median comparison | Add "Mediana do Setor" column to percentile table. Reuses screener sector mode (peer tickers) + compute_all_ratios. |
| P2 | H8 — Period selector (TTM/Annual/Quarterly) | Global toggle switching dashboard between TTM, annual (last DFP), quarterly (last ITR). Thread `period` param through summary() + engine *_at calls. |
| P2 | H9 — Real returns (Fisher equation) overlay | Toggle on price chart: real = (1+nominal)/(1+IPCA) - 1. BCB SGS series 433 already synced. |
| P2 | H10 — Macro overlay on stock charts | "Sobrepor: Selic / CDI / IPCA / Nenhum" dropdown on price chart, secondary y-axis. |
| P3 | H1 — Trend line charts | Line chart per metric showing 5Y time series (DONE v1.15 — keep for reference) |
| P3 | H3 — Export to xlsx | Export percentile + trend tables to Excel |
| Done | v1.19 Beta display + precision + F7 cache | Collective LLM review fixes |
| Done | v1.18 Growth + Beta + COE dashboard | 8 tabs, 17 KPIs, Market Risk tab |
| Done | v1.14 dashboard reorg | 3→5 tabs: subtabs by category, F7 speed fix, charts, ratio_grid |
| Done | Sync guard (v1.14) | required_sources wired via make_route() |
| Done | F7 engine cache (v1.9) | Inherited from calculations skill |
| Done | Subtabs by category (v1.14) | Valuation / Profitability subtab split |
| Done | More metrics (v1.16/v1.17) | Leverage + Efficiency + Growth + Market Risk tabs |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).
> Feature suggestions H6-H10 sourced from external LLM review (Claude 1,
> Claude 2, Qwen, Mistral) of commits e8f8962 + e7763c2.

## 📋 Backlog

### H6 — WACC + DCF Intrinsic Value

**Priority:** P1

Add a WACC engine (COE × E/(D+E) + after-tax Kd × D/(D+E)) and DCF intrinsic
value metric (FCFF discounted at WACC + terminal value → per-share value vs
current price). Closes the valuation loop — users see if a stock is
under/overvalued relative to intrinsic value, not just historical percentile.

**Reuses:** `coe_at`, `debt_periods`, `ebit_periods`, `capex_periods`,
`tax_at`, `shares_periods`, `price_at` — all already built.

**Placement:** new "Valuation Intrínseca" tab in "Avaliação" group.

### H7 — Sector Median Comparison

**Priority:** P1

For each metric in the percentile table, add a "Mediana do Setor" column
showing the median across peer companies in the same B3 sector. A P/L of 15x
might look cheap historically (25th pct) but expensive vs sector median of 12x.

**Reuses:** `build_company_header` (sector field), screener `sector` mode
(peer tickers), `compute_all_ratios` (peer ratios).

**Placement:** "vs Setor" subtab per metric category.

### H8 — Period Selector (TTM / Annual / Quarterly)

**Priority:** P2

Global toggle switching the dashboard between TTM, annual (last DFP), and
quarterly (last ITR) views. Some metrics (revenue growth, margins) are more
meaningful annually; others (beta, price ratios) are period-independent.

**Implementation:** `period` param on `dashboard()`, threaded through to
`summary()` + engine `*_at(company, date)` calls.

### H9 — Real Returns (Fisher Equation) Overlay

**Priority:** P2

Add a "Real Return" toggle on the price chart:
`real = (1 + nominal) / (1 + IPCA) - 1`. Brazilian investors need to know if
they're beating inflation. BCB SGS series 433 (IPCA monthly) is already synced.

**Placement:** toggle button next to "Tudo/5A/1A/1M" on the existing price
chart; overlay IPCA cumulative line.

### H10 — Macro Overlay on Stock Charts

**Priority:** P2

Add a "Sobrepor: Selic / CDI / IPCA / Nenhum" dropdown on the price chart,
drawing a second line on a secondary y-axis. Shows the macro environment the
stock operated in — underperformance might coincide with a Selic hike cycle.

**Reuses:** BCB SGS series 11/12/433 already synced.

### H3 — Export to xlsx

**Priority:** P3

Export the percentile + trend tables to Excel via the report tool's
xlsx adapter. Would need a `historical_dashboard` adapter that maps
each tab to a sheet.

---

*Last updated: 2026-08-06. See [CHANGELOG.md](CHANGELOG.md) for version history.*
