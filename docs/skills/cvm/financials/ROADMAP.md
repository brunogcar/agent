<- Back to [Financials Overview](../FINANCIALS.md)

# 🗺️ Financials ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | F2 — Comparison tab | Company vs sector medians (needs reusable sector-median computation) |
| P2 | F15 — WACC drivers decomposition | Show COE, Kd, E/(D+E), tax shield as a stacked breakdown of WACC |
| P2 | F16 — Quality of Earnings chart | NI vs OCF divergence (5Y line chart, accruals red-flag) |
| P2 | F17 — Capital allocation score | FCF usage breakdown: dividends vs buybacks vs debt paydown vs capex |
| P3 | F5 — Cross-skill dashboard | Unified company profile (financials + valuation + governance + insider) |
| P3 | F18 — Sector-specific ratios | Banks: NIM, Basel; Insurers: combined ratio; REITs: FFO/AFFO |
| P3 | F6 — Real-data verification script | Nightly script: null-rate, consistency checks, PL source breakdown |
| Done | Comprehensive Períodos tables (v2.3) | Multi-section tables (Balanço/DRE/DFC/9 Indicadores sub-tables) with frozen columns + accounts fallback |
| Done | Unified chart color scheme (v2.3) | Receita=orange, EBITDA=magenta, Lucro=purple, margins=maroon/pink shades, DFC=cyan/orange/rose |
| Done | DRE/DFC chart revamp (v2.3) | Line→bar, new colors, _fixedYWidth alignment, R$ (mi) values |
| Done | Overview subtabs (v2.3) | 4 subtabs: Cotação & Resumo, Trajetória Anual, Análise de Risco, Visão Multidimensional |
| Done | Trimestral YoY restructure (v2.3) | Per-quarter subtabs (T1-T4) with same table+chart pattern as other tabs |
| Done | Indicator charts (v2.3) | 3 new bar charts per tab: Liquidez, Disponibilidades/Endividamento, EBIT/EBITDA/CAPEX |
| Done | Frozen columns (v2.3) | Código+Descrição sticky with section header colspan=2 |
| Done | F3 — Price history overlay (v1.23) | COTAHIST daily price on DRE/DFC/DVA charts (dual Y-axis) |
| Done | F4 — Period selector (v1.24) | Trimestral/Anual toggle (pre-render + JS toggle) |
| Reverted | TTM toggle (v2.1 → v2.2) | 3rd "TTM" panel on DRE/DFC/DVA period_toggle was reverted in v2.2 — TTM data stays in the standalone "Anualizado" tab only (cleaner UX, avoids duplicate TTM views) |

> **Note:** Recently completed items (F1–F14, force sync guard, review-fix sprint, dashboard reorg, TTM+YoY, dashboard v3 sprint, collective-review sprint) are in [CHANGELOG.md](CHANGELOG.md).

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

### TTM toggle — ⏮ Reverted (v2.1 → v2.2)

**Priority:** ~~P2~~ Reverted in v2.2.
**Source:** Reviewer suggestion (v2.1 sprint) → user feedback (v2.2)

v2.1 added a 3rd "TTM" (trailing twelve months) panel to the period_toggle
on flow-statement tabs (DRE/DFC/DVA). TTM at quarter Q = rolling 4-
quarter sum (e.g. TTM at 2T2026 = Q3 2025 + Q4 2025 + Q1 2026 + Q2 2026).
Deseasonalizes quarterly noise so the user can see real trends.

v2.2 reverted this — the 3-panel toggle duplicated the TTM data already
available in the standalone "Anualizado" tab, and the user preferred to
keep TTM in one place. The revert:
  - Removed ``ttm_periods`` + ``ttm_chart`` params from
    ``_build_period_toggle_sections()`` in ``report/statements.py``.
  - Removed ``ttm_periods`` param from ``build_dre_sections`` /
    ``build_dfc_sections`` / ``build_dva_sections``.
  - Removed the TTM normalization block + the 3 ``ttm_periods=`` kwargs
    from ``dashboard.py``.
  - Reverted the ``period_toggle`` macro in ``macros.html`` to 2-button
    mode (Trimestral + Anual).
  - Removed the TTM panel chart-render loops from ``dashboard.html``.
  - Kept ``build_ttm_table`` + ``build_ttm_chart`` in ``report/periods.py``
    for the standalone "Anualizado" tab (unchanged).

### F15 — WACC drivers decomposition

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint)

Show WACC decomposed into its 4 drivers: COE (cost of equity), Kd (cost
of debt, after-tax), E/(D+E) (equity weight), tax shield (1 − t ×
D/(D+E)). Currently the dashboard shows WACC as a single number in the
Overview tab; this enhancement adds a small waterfall/bar chart breaking
WACC into its components so the user can see which driver dominates
(e.g. high COE pushing WACC up vs low Kd + high leverage pulling it
down). Requires the WACC engine to expose its component values (COE,
Kd_pre, tax_rate, E, D) — check `calculations/engines/wacc/` for what's
already available.

### F16 — Quality of Earnings chart

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint)

5Y line chart showing Net Income vs Operating Cash Flow divergence.
When NI grows but OCF flatlines or declines (or persists below NI), it
indicates low earnings quality (aggressive accruals, unrealized
receivables). Already partially built as `_build_dfc_fco_vs_ll_chart`
(inside the period_toggle) — this enhancement promotes it to a
standalone analytical section in the Overview tab with an "accruals
ratio" = (NI − OCF) / |NI| computed + flagged red when > 0.3 for 2+
consecutive years.

### F17 — Capital allocation score

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint)

Show how the company deploys its Free Cash Flow: dividends paid,
buybacks, debt paydown, capex, M&A. Requires the DFC engine to break
out capex (already done — `capex_at`), dividends paid (DVA 7.08.04 —
already done), buybacks (BPP code 2.03.06 — needs engine), debt
paydown (BPP codes 2.01.04 + 2.02.01 delta — needs engine). A simple
stacked-bar chart showing 5Y of FCF usage breakdown. The "score" is
the % allocated to value-creating uses (capex growth + buybacks when
undervalued + debt paydown when over-leveraged) vs value-destroying
(dividends > FCF, M&A at premiums).

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

### F18 — Sector-specific ratios

**Priority:** P3
**Source:** Reviewer suggestion (v2.1 sprint)

Add sector-specific ratios computed only when the company's setor
matches a known sector type:
  - **Banks** (Banco): NIM (Net Interest Margin), Basel ratio, Loan-to-
    Deposit, Cost-to-Income. Needs DRE codes specific to banks (16.01,
    16.02, etc. — banks use a different DRE taxonomy).
  - **Insurers** (Seguros): Combined Ratio = (Losses + Expenses) /
    Earned Premiums. Needs DRE codes specific to insurers.
  - **REITs** (Fundos Imobiliários): FFO (Funds From Operations), AFFO
    (Adjusted FFO). Needs DFC + DRE adjustments.

**Blocker:** the financials skill currently assumes the standard DRE
taxonomy (3.01 Receita, 3.09 Lucro). Banks + insurers use different
codes — the `bpa_section_for` / `dre_section_for` resolvers would need
sector-specific variants, or a sector-detection step that swaps in the
correct taxonomy. Cross-skill coordination: the `comparison` skill
already has sector-aware logic that could be reused.

---

*Last updated: 2026-08-13 (v2.2 — TTM toggle reverted; standalone "Anualizado" tab kept. F3 + F4 DONE). See [CHANGELOG.md](CHANGELOG.md) for version history.*
