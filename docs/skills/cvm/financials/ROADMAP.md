<- Back to [Financials Overview](../FINANCIALS.md)

# 🗺️ Financials ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | F2 — Comparison tab | Company vs sector medians (needs reusable sector-median computation) |
| P3 | F5 — Cross-skill dashboard | Unified company profile (financials + valuation + governance + insider) |
| P2 | F6 — Real-data verification script | Nightly script: null-rate, consistency checks, PL source breakdown |
| Done | F3 — Price history overlay (v1.23) | COTAHIST daily price on DRE/DFC/DVA charts (dual Y-axis) |
| Done | F4 — Period selector (v1.24) | Trimestral/Anual toggle (pre-render + JS toggle) |

> **Note:** Recently completed items (F1–F14, force sync guard, review-fix sprint, dashboard reorg, TTM+YoY, dashboard v3 sprint, collective-review sprint) are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Next: Valuation Skill Overhaul

The financials dashboard v3 pattern (company header + price chart + sidebar
groups + tooltips + chart titles + freshness footer) is now the template
for all CVM skill dashboards. **Next commit** will apply the same pattern
to the `valuation` skill:

1. **Company header** — reuse `build_company_header()` from `skills/cvm/_shared_report/`
2. **Historical price chart** — reuse `build_price_chart()` from `skills/cvm/_shared_report/`
3. **Sidebar groups** — Resumo / Múltiplos / Fundamentos / Crescimento
4. **Chart titles + descriptions** — on all existing charts
5. **Tooltips** — reuse `get_tooltip()` from `skills/cvm/_shared_report/`
6. **Freshness footer** — compact, replaces bulky tables
7. **engine_cache_scope** — wrap dashboard in cache scope
8. **New mode: historical_valuation** — P/L, EV/EBITDA over time (mirrors financials TTM pattern)

See the valuation skill's own [ROADMAP.md](../valuation/ROADMAP.md) for details.

## 📋 Backlog

### F2 — Comparison tab (company vs sector medians)

**Priority:** P2
**Source:** Claude 2 + Qwen + Minimax reviews (all 3 suggested)

Add an 8th dashboard tab "Comparação" showing the company's key metrics
side-by-side with sector median/percentile. Requires a reusable
sector-median computation:

  1. Resolve the company's setor (BDR/Setor/Subsetor from FCA or CAD).
  2. Fetch all companies in that setor.
  3. Compute median + 25th/75th percentile for ROE, ROIC, Margem Líquida,
     Dívida Líquida/EBITDA, P/L, EV/EBITDA.
  4. Show a two-column table: [Metric, Company, Sector Median, Percentile].

**Blocker:** the `comparison` skill already does peer comparison but
returns a different payload shape. Need a thin adapter or a shared
`sector_medians()` helper in `calculations/`.

### F3 — Price history overlay (COTAHIST integration) — ✅ Done (v1.23)

**Priority:** ~~P2~~ Done in v1.23.
**Source:** Claude 2 review

Overlay the company's daily closing price on the DRE/DFC/DVA trend
charts (dual Y-axis: BRL statement values on left, BRL share price on
right). Implemented via `_fetch_year_end_prices()` + `_attach_price_overlay()`
in `report/overview.py` — dual-axis Chart.js config (`scales.y` for
statements + `scales.y1` for price, `position: 'right'`). Used on the
Overview trend chart (v1.23) and the DRE/DFC/DVA per-statement trend
charts (v1.23).

### F4 — Period selector (Trimestral/Anual toggle) — ✅ Done (v1.24)

**Priority:** ~~P2~~ Done in v1.24.
**Source:** Qwen review

Period selector (Trimestral/Anual) implemented as a pre-render + JS
toggle in v1.24. The dashboard pre-renders BOTH annual + quarterly
statement tables, wraps them in `_build_period_toggle_sections()`
(`report/statements.py`), and the frontend `togglePeriod` JS swaps
visibility (calling `chart.resize()` on the now-visible panel so charts
render correctly inside `display:none` containers — see INSTRUCTIONS.md
v1.25 lesson). Period labels use `"2T2026"` format; up to 20 quarterly
periods fetched via `_fetch_all_statements_quarterly()`.

### F5 — Cross-skill dashboard

**Priority:** P3
**Source:** Claude 2 review

A unified dashboard that composes financials + valuation + governance +
insider + shareholders into a single "company profile" view. Each skill's
dashboard becomes a collapsible section (or a top-level tab in a master
dashboard). Requires:

  - A `company_profile()` orchestrator (in a new skill or in `core/`).
  - A shared `company` resolver (already exists via `_bridge.resolve_company`).
  - Template support for nested tab levels (current template supports 2
    levels: tabs → subtabs; this would need tabs → subtabs → sections).

### F6 — Standing real-data verification script

**Priority:** P2
**Source:** Claude 2 review (CRITICAL for data-quality confidence)

A standalone script (`scripts/verify_real_data.py`) that runs the
dashboard against REAL CVM data (not the synthetic test DB) for a set of
well-known tickers (PETR4, VALE3, ITUB4, etc.) and reports:

  - Which metrics returned None (null-rate per metric).
  - Cross-statement consistency check results (DVA 7.08 ≈ sum of
    7.08.01-7.08.04; DRE 3.03 ≈ 3.01 - 3.02; etc.).
  - PL source_code breakdown (how many snapshots used the 2.08 fallback).
  - Growth gap-tolerance bridge rate (how often the prior was found
    outside the ideal lookback but within the tolerance window).

**Purpose:** catches silent data-quality regressions before users see
broken dashboards. Should run nightly (cron) in production.

---

*Last updated: 2026-08-13 (v2.0 — report/ package split + v1.17-v1.25 features; F3 + F4 marked Done; F1, F7–F14 moved to CHANGELOG). See [CHANGELOG.md](CHANGELOG.md) for version history.*
