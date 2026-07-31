<- Back to [Financials Overview](../FINANCIALS.md)

# 🗺️ Financials ROADMAP

Living roadmap for the financials skill. Items here are inspired by LLM
review findings (Claude 2, Qwen, Minimax) on the v1.12 dashboard reorg +
the v1.13 review-fix sprint. Items move from **Backlog** → **In
Progress** → **Completed** (then they appear in CHANGELOG.md).

The v1.13 review-fix sprint (this commit) addressed 5 P1/P2 findings:
subtab chart rendering, `_pick_pl_value()` zero-value trap, period-specific
growth gap tolerance, Indicadores sub-tab split, and DVA doughnut
percentages. The items below are the REMAINING backlog from those reviews.

---

## 🚧 In Progress

(none — v1.13 review-fix sprint complete; next up is Backtest/Historical/
Investsite dashboard reorg.)

---

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

### F7 — Performance: per-call engine caching in compute_all_ratios()

**Priority:** P1
**Source:** Performance audit (user request)

`compute_all_ratios()` currently calls each metric's `ratio_fn`, which
calls each engine's `at_fn`, which opens a DB connection + runs a query.
For a dashboard with 35+ metrics, many engines are called redundantly
(e.g., `earnings` is used by ROE, ROIC, sustainable_growth, LPA, DPA,
earnings_yield). A per-call cache keyed by `(engine_name, company, date)`
reduces DB queries by 40-60%.

**Implementation:** add an LRU cache dict scoped to a single
`compute_all_ratios()` invocation (cleared at the end). Pass it as a
`_cache` kwarg to each `at_fn`, or use a contextvar.

### F8 — Performance: materialized ratios table

**Priority:** P2
**Source:** Performance audit (user request)

Pre-compute all ratios on sync (when DFP/ITR/FRE data is refreshed) and
store in a `ratios_materialized` table. Dashboard queries become
single-row lookups instead of 35 engine calls.

**Schema:**
```sql
CREATE TABLE ratios_materialized (
  ticker TEXT, date TEXT,
  roe REAL, roa REAL, roic REAL, ... -- one column per metric
  computed_at TEXT,
  PRIMARY KEY (ticker, date)
);
```

**Trade-off:** adds sync-time compute cost + staleness (ratios are
point-in-time at sync, not at query). Best for read-heavy dashboards.

---

## ✅ Recently Completed

(See [CHANGELOG.md](CHANGELOG.md) for the full version history.)

- **v1.13 (review-fix sprint)** — 5 LLM-review fixes: (1) recursive
  subtab chart rendering in dashboard.html, (2) `_pick_pl_value()` with
  `!= 0` check + 2.08 fallback (description-checked), (3) period-specific
  growth gap tolerance (1.5x for 3M/1Y, 1.2x for 5Y) via new
  `growth_helpers.py`, (4) Indicadores tab split into category sub-tabs,
  (5) DVA doughnut tooltip percentages via `_tooltipPercent` flag.
- **v1.12** — 7-tab dashboard reorg (Overview / Indicadores / Crescimento
  / Balanço / DRE / DFC / DVA) with sub-tabs, charts, collapsibles.
- **v1.6** — File structure split + valuation dashboard mode.

---

*Last updated: v1.13 review-fix sprint (subtab charts + PL zero-value
trap + growth gap tolerance + Indicadores sub-tabs + DVA percentages).*
