<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Valuation ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | D1 — Per-statement adapters | BPA/BPP/DRE/DFC/DVA adapters for Per-share tab |
| P2 | D2 — Additional metrics | ROI, COE/CAPM, CAGR, Earnings Yield, P/Ativos, P/Passivos, P/RB |
| P2 | D3 — Cash flow metrics | FCT, FCL, Saldo Inicial/Final |
| P3 | D4 — New data sources | B3 index, Beta, options, volatility, BCB macro, FX rates |
| P2 | D5 — Dashboard enhancements | Sub-tabs, price trend, margin trend, peer comparison |
| P2 | D6 — Report adapters | valuation_bpa/bpp/dre/dfc/dva/macro |
| P3 | D7 — Performance & quality | Per-call cache done (F7); materialized done (F8); TypedDict + telemetry remaining |
| Next | Backtest/Historical/Investsite dashboard reorg | Apply v1.12 dashboard pattern to 3 more skills |
| Done | F7 engine cache (v1.9) | `@engine_cached` decorator — ~60% fewer DB queries |
| Done | F8 materialized ratios (v1.10) | Pre-computed fundamentals in SQLite — event-driven on sync |
| Done | Force sync guard (v1.7) | `ensure_fresh()` + HEAD check + current-year force sync |

---

## ✅ Recently Completed

- **v1.7 (2026-07-31)** — Force sync guard. `__init__.py` passes
  `required_sources=["dfp","itr","fca","cotahist","bridge"]` to `make_route()`.
  route() calls `ensure_fresh()` before dispatch. HEAD check for CVM sources.
  Re-entrancy guard. Escape hatches: `CVM_SKIP_SYNC=1` + `skip_sync=True`.
- **v1.5 (2026-07-29)** — 6-tab dashboard reorg: added Per-share tab,
  charts, collapsibles, `_derive_*()` helpers.

---

Living roadmap for the valuation skill. Items here are inspired by a private
valuation spreadsheet analysis (covering B3 stocks comprehensively) + by
gaps surfaced during the v1.5 6-tab dashboard reorg. Items move from
**Backlog** → **In Progress** → **Completed** (then they appear in
CHANGELOG.md).

The dashboard's v1.5 Multiples tab already lists all 16 price ratios in
its top-10 table + "Less Common Multiples" collapsible — but several of
those keys (P/Ativos, P/Passivos, P/RB, etc.) currently render as `—`
because the underlying engines/metrics aren't wired into `ratios()`. The
roadmap items below close that gap.

---

## 🚧 In Progress

### D1 — Per-statement report adapters (BPA / BPP / DRE / DFC / DVA)

Today the report tool exposes `valuation_ratios` + `valuation_summary`
adapters. To populate the dashboard's Per-share tab fully (LPA, VPA, DPA,
RPA, RBPA, CGPA, DBPA, APA, PPA), the dashboard needs access to BPA
(total_assets) + BPP (total_liabilities) + DRE (gross_revenue / receita
bruta) engines. Two paths:

- **A — Generic statement adapter**: a single `valuation_statement`
  adapter that calls `financials.bpa|bpp|dre|dfc|dva` for the latest
  period + reshapes into the dashboard's per-share + multiples tabs.
- **B — Per-statement adapters**: 5 thin adapters (`valuation_bpa`,
  `valuation_bpp`, ...) — mirrors the financials pattern, more flexible
  for callers that want a single statement.

The dashboard already uses the **financials** standalone statement modes
in its own tab building (see `historical/modes/dashboard.py` for the
template). For valuation, we'd want a thinner approach: pull only the
codes needed for per-share + multiples derivation, not the full
statement.

**Status:** Backlog → In Progress once D2 lands (engines first, adapters
second).

---

## 📋 Backlog

### D2 — Additional calculation metrics

Wire these new metrics into `skills/cvm/calculations/metrics/` so they
flow through `compute_all_ratios()` automatically (no `ratios()` edits
needed):

| Metric | Formula | Notes |
|--------|---------|-------|
| **ROI** (Return on Investment) | NOPAT / Invested Capital | Like ROIC but uses invested-capital-at-book. Reuses `ebit`, `pl`, `debt`, `cash` engines. |
| **COE** (Cost of Equity / CAPM) | Rf + β × (Rm − Rf) | Needs Beta (see D3) + risk-free rate (see D6 — Selic or CDI as proxy). |
| **CAGR** (Compound Annual Growth Rate) | (V_end / V_start)^(1/n) − 1 | Per-metric, over 3Y / 5Y windows. Needs historical earnings + revenue + equity engines. |
| **Earnings Yield** | 1 / P/L (i.e. EPS / price) | Trivial from `p_l`. Useful for comparing stocks vs bonds (inverse of P/L). |
| **P/EBITDA** | market_cap / ebitda | Already computed via `_derive_multiples()` in `report.py` v1.5 — promote to a registered metric for canonical use. |
| **EV/EBIT** | ev / ebit | Same as above. |
| **P/EV** | market_cap / ev | Same. |
| **P/CG** (Price / Working Capital) | market_cap / working_capital | Same. |
| **P/DB** (Price / Gross Debt) | market_cap / divida_bruta | Same. |
| **P/Ativos** | market_cap / total_assets | Needs `total_assets` engine (already exists in calculations/engines/total_assets.py — just not consumed by ratios()). |
| **P/Passivos** | market_cap / total_liabilities | Needs a total_liabilities engine. Could derive = total_assets − patrimonio_liquido, but a dedicated engine is cleaner. |
| **P/RB** (Price / Receita Bruta) | market_cap / gross_revenue | Needs `gross_revenue` engine. Currently `revenue` engine returns receita líquida (net revenue) — gross_revenue requires DRE account 3.01 (Receita Bruta de Vendas). |
| **DL/EBIT** (Net Debt / EBIT) | (divida_bruta − caixa) / ebit | Already computed via `_derive_detailed_leverage()` in `report.py` v1.5 — promote to a registered metric. |
| **Gross Debt/Equity** | divida_bruta / patrimonio_liquido | Same — promoted from `_derive_detailed_leverage()`. |
| **Financial Leverage** | total_assets / patrimonio_liquido | Needs total_assets engine. Different from debt_equity (which is debt-only). |

### D3 — Additional cash flow metrics

| Metric | Formula | Notes |
|--------|---------|-------|
| **FCT** (Total Cash Flow) | FCO + FCI + FCF (financing) | Currently only FCO + FCI are wired; FCF (financing CF) needs the `financing_cf` engine (already exists at calculations/engines/financing_cf.py — not yet consumed by ratios()). |
| **FCL** (Free Cash Flow = FCO − CAPEX) | FCO − capex | Currently FCF = FCO + FCI (investing CF, includes more than just CAPEX). FCL is the "true" free cash flow. Needs the `capex` engine (already exists — not consumed). |
| **Saldo Inicial / Saldo Final** (cash balance start / end of period) | snapshot at t-1 / t | From DFC account 5.05 (Caixa Líquido). Useful for cash-position dashboard widgets. |

### D4 — New data sources

These are entirely new data sources — not yet wired into any engine.

| Source | What | Use Case |
|--------|------|----------|
| **B3 index participation** (IBOV / SMALL / IDIV) | ticker → weight in each index | "PETR4 is 8% of IBOV" → benchmarking + liquidity signal. From B3's `IndexReport` file (daily). |
| **Beta (5-year)** | β vs IBOV | For COE/CAPM (D2). Computed from weekly returns regression. Could be a calculations engine that composes `price` + `index` engines. |
| **Options data** (Call/Put counts, PM, ratio) | open interest per strike, put/call ratio, preço médio (PM) | Options sentiment widget. From B3 `OpcaoInformativo` (daily). |
| **Price volatility** (Daily / Weekly / Monthly min/max/avg) | rolling volatility windows | Risk dashboard widget. Computed from COTAHIST historical prices. |
| **Annual returns history** | YTD / 1Y / 3Y / 5Y total return | Performance widget. Computed from COTAHIST + dividends. |
| **Macro indicators** (Selic, CDI, IPCA, IGP-M) | time series via BCB SGS API | Risk-free rate (Selic/CDI) for COE. Inflation (IPCA/IGP-M) for real returns. BCB SGS is a public JSON API — no auth. |
| **Dollar / Euro rates** (USD/BRL, EUR/BRL) | daily FX | For translating BRL statements to USD comparisons. Source: BCB SGS (PTAX) or brapi. |

### D5 — Dashboard enhancements

| Enhancement | Tab | Notes |
|-------------|-----|-------|
| **Sub-tabs within tabs** | Multiples (Valuation / EV / Per-share), Liquidity (Liquidity / Leverage / Detailed) | The template supports `type: "subtabs"` already. Wrap existing sections. |
| **Price trend chart** | Overview | 1Y / 3Y / 5Y daily price line chart (from COTAHIST historical). |
| **Margin trend chart** | Profitability | 5Y margins line chart (gross / operating / net / EBITDA). Needs historical DRE periods. |
| **Growth trend chart** | Efficiency & Growth | Currently `—` placeholders — implement once D2 (CAGR) + historical engines land. |
| **Collapsible sections for detailed metrics** | All tabs | Template supports `type: "collapsible"` — used for Price Details, Less Common Multiples, Detailed Leverage. Extend to other tabs (e.g. a "5Y quartile summary" collapsible on each multiples row). |
| **Statement sub-tab** | New tab "Statements" | Embed BPA / BPP / DRE / DFC / DVA as 5 sub-tabs. Mirrors `financials.dashboard()` v1.12 Balanço tab. |
| **Comparison mode** | New tab "Peer Comparison" | Side-by-side multiples vs sector peers (reuses `comparison` skill). |

### D6 — Report tool adapters

| Adapter | What it tables |
|---------|----------------|
| `valuation_bpa` | Latest BPA accounts (Ativo) + P/Ativos, P/Tangible Book derived |
| `valuation_bpp` | Latest BPP accounts (Passivo + PL) + P/Passivos, D/E, Gross D/E |
| `valuation_dre` | Latest DRE accounts + P/RB, P/EBIT, P/EBITDA, margins |
| `valuation_dfc` | Latest DFC accounts + P/FCO, P/FCF, FCT, FCL, Saldo Inicial/Final |
| `valuation_dva` | Latest DVA accounts + wealth distribution doughnut chart |
| `valuation_macro` | Macro indicators (Selic / CDI / IPCA / IGP-M / USD-BRL / EUR-BRL) snapshot |

### D7 — Performance & quality

| Item | Priority | Notes |
|------|----------|-------|
| ~~Per-call engine caching in `compute_all_ratios()`~~ | ~~P1~~ | ✅ **Done (v1.9 F7)** — `@engine_cached` decorator + `engine_cache_scope` ContextVar. ~60% fewer DB queries. |
| ~~Materialized ratios table~~ | ~~P2~~ | ✅ **Done (v1.10 F8)** — `ratios_materialized` table in `memory_db/cvm/ratios.db`. Only stable fundamentals materialized; growth + price-based stay live. Event-driven invalidation on sync. |
| **Cache `ratios()` per (ticker, day)** | P2 | Currently every dashboard call re-queries every engine. Add a TTL cache (5 min?) keyed by (ticker, today). Complements F7 (per-call cache) by extending the cache boundary to cross-call. |
| **Type-hint the ratios dict** | P3 | Currently `dict[str, Any]`. Define a `ValuationRatios` TypedDict so downstream skills get autocomplete + mypy checking. |
| **Telemetry** | P3 | Count how often each metric returns None (per engine). Surface in summary() as `null_rate` per metric. |

---

## ✅ Recently Completed

(See [CHANGELOG.md](CHANGELOG.md) for the full version history.)

- **v1.5 (2026-07-29)** — 6-tab dashboard reorg: added Per-share tab,
  added charts (Multiples bar chart, Per-share bar chart, planned
  Efficiency & Growth growth chart), added collapsibles (Price Details,
  Less Common Multiples, Detailed Leverage), added `_derive_multiples()`
  + `_derive_per_share()` + `_derive_detailed_leverage()` helpers that
  compute additional metrics from components already in ratios_dict.
- **v1.4 (2026-07-29)** — File structure split + 5-tab dashboard mode.
- **v1.3 (2026-07-29)** — Registry-driven ratios via compute_all_ratios().
- **v1.2 (2026-07-29)** — Wired 15 v1.3 calculations metrics into ratios().

---

*Last updated: 2026-07-31 (v1.7 — force sync guard + F7 engine cache + F8 materialized ratios). See [CHANGELOG.md](CHANGELOG.md) for version history.*
