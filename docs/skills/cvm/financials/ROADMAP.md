<- Back to [Financials Overview](../FINANCIALS.md)

# 🗺️ Financials ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | F1 — Chart serialization test | Regression test for JSON-serializable chart_data |
| P2 | F2 — Comparison tab | Company vs sector medians (needs reusable sector-median computation) |
| P2 | F3 — Price history overlay | COTAHIST daily price on DRE/DFC/DVA charts (dual Y-axis) |
| P2 | F4 — Period selector | TTM toggle plumbing (annual/TTM/quarterly dropdown) |
| P3 | F5 — Cross-skill dashboard | Unified company profile (financials + valuation + governance + insider) |
| P2 | F6 — Real-data verification script | Nightly script: null-rate, consistency checks, PL source breakdown |
| Next | Backtest/Historical/Investsite dashboard reorg | Apply v1.12 dashboard pattern to 3 more skills |
| Done | F7 — Engine cache (v1.9) | `@engine_cached` decorator — ~60% fewer DB queries |
| Done | Force sync guard (v1.14) | `ensure_fresh()` + HEAD check + current-year force sync |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### F1 — Chart serialization test

**Priority:** P2
**Source:** Minimax review (v1.13 finding)

Add a regression test that verifies every `chart_data` dict produced by
`report.py` builders is JSON-serializable (survives `| tojson` in Jinja).
The v1.5 template-overhaul sprint hit a crash where `"callback":
"{}%".format` (a method, not a string) silently broke chart rendering.
A standing test prevents this class of bug.

**Test shape:** call each `build_*_sections()` function with mock data,
collect every `section["chart_data"]`, and assert `json.dumps()` succeeds
on each. Also assert no `chart_data` value is a function/method/lambda
(use `isinstance(v, (str, int, float, bool, type(None), list, dict))`
recursively).

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

### F3 — Price history overlay (COTAHIST integration)

**Priority:** P2
**Source:** Claude 2 review

Overlay the company's daily closing price on the DRE/DFC/DVA trend
charts (dual Y-axis: BRL statement values on left, BRL share price on
right). Requires the COTAHIST historical price feed:

  - The `price` engine already exists (`calculations/engines/price.py`)
    and reads from a cotahist-derived DB.
  - Need a `price_series(ticker, date_from, date_to)` call in the chart
    builder, normalized to the statement period dates.
  - Dual-axis Chart.js config: `scales.y` (statements) + `scales.y1`
    (price, `position: 'right'`).

**Blocker:** COTAHIST sync must be confirmed working in the target env
(the price engine returns `[]` in test envs without a cotahist DB).

### F4 — Period selector (TTM toggle plumbing)

**Priority:** P2
**Source:** Qwen review

Add a period-selector dropdown to the dashboard (Annual / TTM /
Quarterly) that re-fetches statement data with the chosen period mode.
Currently the dashboard hardcodes `period="annual"` for all 5 statement
modes. The toggle needs:

  1. A `period` param on `dashboard()` (default `"annual"`).
  2. Plumbing through to `_call_bpa/bpp/dre/dfc/dva`.
  3. Frontend: a `<select>` in the sidebar that triggers a re-fetch (or
     pre-renders all 3 variants and toggles visibility via JS).

**Design note:** pre-rendering 3 variants triples the payload size.
Better to make `dashboard()` accept `period` and let the caller
(report tool) re-render on change.

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

*Last updated: 2026-08-01. See [CHANGELOG.md](CHANGELOG.md) for version history.*
