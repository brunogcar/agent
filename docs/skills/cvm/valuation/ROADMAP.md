<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Valuation ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | V1 — WACC drivers decomposition | Show COE, Kd, E/(D+E), tax shield as a stacked breakdown of WACC (mirrors financials F15) |
| P2 | V2 — Sector medians / peer comparison | Side-by-side multiples vs sector medians + percentiles (reuse comparison skill) |
| P2 | V3 — Statement sub-tab | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs (mirror financials v1.12 Balanço pattern) |
| P3 | V4 — Cross-skill unified dashboard | Unified company profile (financials + valuation + governance + insider) |
| P3 | D3 — Cash flow metrics (remaining) | Saldo Inicial/Final (cash balance start/end of period from DFC 5.05). FCT + FCL done v1.11. |
| P3 | D6 — Report adapters | valuation_bpa/bpp/dre/dfc/dva/macro |
| P3 | Statement sub-tab | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs (mirror financials v1.12 Balanço pattern) |
| P3 | Peer Comparison tab | Side-by-side multiples vs sector peers (reuse comparison skill) |
| P3 | TypedDict for ratios | Define `ValuationRatios` TypedDict for mypy + autocomplete |
| P3 | Telemetry | Count null_rate per metric in summary() |
| Done | Selic series 432 (v2.0) | Switched BCB series 11 → 432 (Meta Selic Copom % a.a.) — series 11 returned corrupt compound values |
| Done | CAGR key fix (v1.25) | Fixed `_cagr_at()` key mismatch — was looking for `value`/`revenue`/`ttm`/`gross_profit` but `revenue_periods()` returns `ttm_rev` + `gross_profit_periods()` returns `ttm_gp` |
| Done | DCF CAGR 3Y growth (v2.1) | DCF base_growth now uses CAGR 3Y (capped at 8%) instead of volatile `revenue_growth_1y` — stabilizes DCF intrinsic value across cycles |

> **Note:** Completed items live in [CHANGELOG.md](CHANGELOG.md). This file
> lists only true backlog + in-progress items.

---

## 📋 Backlog

### D3 — Cash flow metrics (remaining)

**Status:** FCT + FCL done in v1.11. Saldo Inicial/Final remaining.

| Metric | Formula | Status | Notes |
|--------|---------|--------|-------|
| **FCT** (Total Cash Flow) | FCO + FCI + FCF (financing) | ✅ Done (v1.11) | `metrics/fct.py` |
| **FCL** (Free Cash Flow = FCO − CAPEX) | FCO − |CapEx| | ✅ Done (v1.11) | `metrics/fcl.py` |
| **Saldo Inicial / Saldo Final** | snapshot at t-1 / t | Not started | From DFC account 5.05 (Caixa Líquido). Needs a new engine. |

### D6 — Report tool adapters

**Status:** Not started.

| Adapter | What it tables |
|---------|----------------|
| `valuation_bpa` | Latest BPA accounts (Ativo) + P/Ativos, P/Tangible Book derived |
| `valuation_bpp` | Latest BPP accounts (Passivo + PL) + P/Passivos, D/E, Gross D/E |
| `valuation_dre` | Latest DRE accounts + P/RB, P/EBIT, P/EBITDA, margins |
| `valuation_dfc` | Latest DFC accounts + P/FCO, P/FCF, FCT, FCL, Saldo Inicial/Final |
| `valuation_dva` | Latest DVA accounts + wealth distribution doughnut chart |
| `valuation_macro` | Macro indicators (Selic / CDI / IPCA / IGP-M / USD-BRL / EUR-BRL) snapshot |

### D5 — Dashboard enhancements (remaining)

**Status:** Sub-tabs, price trend, growth trend, P/L-LPA history chart, ROE
trend chart, margin trend chart, Graham overlay (removed v1.10) are DONE.

Remaining:

| Enhancement | Tab | Notes |
|-------------|-----|-------|
| **Statement sub-tab** | New tab "Statements" | Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs. Mirrors `financials.dashboard()` v1.12 Balanço tab. |
| **Comparison mode** | New tab "Peer Comparison" | Side-by-side multiples vs sector peers (reuses `comparison` skill). |

### D7 — Performance & quality (remaining)

**Status:** Mostly done. F7 engine cache (v1.9) + persistent DB cache (v1.10
fix) + per-(ticker,day) cache (engine cache DB) all done. Remaining:

| Item | Priority | Notes |
|------|----------|-------|
| **Type-hint the ratios dict** | P3 | Define `ValuationRatios` TypedDict for mypy + autocomplete. |
| **Telemetry** | P3 | Count null_rate per metric in summary(). |

### V1 — WACC drivers decomposition

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint; mirrors financials F15)

Show WACC decomposed into its 4 drivers: COE (cost of equity, via CAPM =
risk-free + β × equity risk premium), Kd (cost of debt, after-tax =
pre-tax × (1 − tax_rate)), E/(D+E) (equity weight), tax shield. The
Valor Intrínseco tab currently shows WACC as a single number; this
enhancement adds a small waterfall/bar chart breaking WACC into its
components so the user can see which driver dominates (high COE pushing
WACC up vs low Kd + high leverage pulling it down). Requires the WACC
engine (`calculations/engines/wacc/`) to expose its component values —
check what `wacc_at()` already returns internally (COE, Kd_pre,
tax_rate, E, D, β, ERP, risk-free).

### V2 — Sector medians / peer comparison

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint)

Add a "Comparação Setorial" tab showing the company's key multiples
side-by-side with sector medians + 25th/75th percentiles. Reuses the
`comparison` skill's peer-comparison logic. Mirrors financials F2 — the
two skills should share a single `sector_medians()` helper in
`calculations/` to avoid duplication. Tab layout: 2-column table
[Metric, Company, Sector Median, Percentile] + a bar chart overlaying
the company's value vs the sector median band.

**Blocker:** the `comparison` skill returns a different payload shape
than what the valuation dashboard expects. Need a thin adapter or shared
`sector_medians()` helper.

### V3 — Statement sub-tab

**Priority:** P2
**Source:** Reviewer suggestion (v2.1 sprint; supersedes the existing
"Statement sub-tab" P3 item above)

Embed BPA/BPP/DRE/DFC/DVA as 5 sub-tabs in a new "Demonstrações" tab —
mirrors the financials skill's v1.12 Balanço tab pattern (subtabs +
period_toggle + multi-period table). Lets valuation users see the raw
statement data without switching to the financials skill. Reuses
`build_balanco_section` / `build_dre_sections` / `build_dfc_sections` /
`build_dva_sections` directly from `skills.cvm.financials.report`. The
[v2.1] TTM toggle added to financials will automatically be available
here too (the period_toggle macro + JS are shared via `dashboard.html`).

### V4 — Cross-skill unified dashboard

**Priority:** P3
**Source:** Reviewer suggestion (v2.1 sprint; mirrors financials F5)

A unified dashboard that composes financials + valuation + governance +
insider + shareholders into a single "company profile" view. Each
skill's dashboard becomes a collapsible section (or a top-level tab in
a master dashboard). Requires:
  - A `company_profile()` orchestrator (in a new skill or in `core/`).
  - A shared `company` resolver (already exists via
    `_bridge.resolve_company`).
  - Template support for nested tab levels (current template supports 2
    levels: tabs → subtabs; this would need tabs → subtabs → sections).

---

## 🚫 Deferred / Out of Scope

- **Options data** (Call/Put counts, PM, ratio) — B3 `OpcaoInformativo` not synced. Would need a new data source.
- **Price volatility windows** — Can be computed from COTAHIST but no engine exists. Low priority.
- **Annual returns history** (YTD/1Y/3Y/5Y total return) — Needs COTAHIST + dividends composition. Low priority.
- **TIR (IRR) from CVM cash flow timing** — Not feasible. (Note: `irr_at` metric EXISTS — it computes IRR from DCF assumptions vs current price, not from CVM cash flow timing.)
- **Sector benchmarks** — ✅ Done via `screener` skill.
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.
- **Materialized ratios table** — F8 was implemented (v1.10) then removed (v1.10.3) because it only cached ~20 of 49 metrics + added overhead. F7 engine cache provides the real speedup. Will not revisit.

---

*Last updated: 2026-08-13 (v2.1 — added V1/V2/V3/V4 backlog items + DCF CAGR 3Y / CAGR key fix / Selic series 432 marked Done). See [CHANGELOG.md](CHANGELOG.md) for version history.*
