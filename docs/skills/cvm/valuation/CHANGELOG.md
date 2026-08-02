<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.8** | 2026-08-02 | **Dashboard overhaul mirroring financials v3 + v2 split tables + historical_valuation mode + Earnings Yield metric.** Applied the financials v3 dashboard pattern to valuation, then refined with split tables + charts per group. **Dashboard overhaul:** (1) Company header (FCA/CAD/COTAHIST) at top of Overview — reuses `build_company_header` from `_shared_report`. (2) Historical price chart with Tudo/5A/1A/1M range selector — reuses `build_price_chart`. (3) Sidebar groups — 5 tabs in 3 groups: Resumo (Overview, Multiples), Fundamentos (Profitability, Liquidity & Leverage), Crescimento (Efficiency & Growth). (4) Per-share tab merged into Multiples. (5) Tooltips on all ratio_grid items — reuses `get_tooltip` from `_shared_report`. (6) Chart titles + descriptions on all charts. (7) Freshness footer. (8) `engine_cache_scope` wraps data-gathering. (9) `value_raw` on all ratio_grid items. **V2 split tables + charts:** (10) Overview — removed Preço/Data/Fonte (in header now), split into 3 tables (Métricas de Mercado, Resultado TTM, Balanço Patrimonial). (11) Multiples — split into 3 groups (Preço, EV, Menos Comuns) each with bar chart. (12) Profitability — split ratio_grid into Retornos + Margens, split chart into Returns + Margins. (13) Liquidity & Leverage — added 2 bar charts, replaced collapsible with detailed table with interpretation. (14) Efficiency & Growth — split into 3 per-metric tables (Receita, Lucro Bruto, Lucro Líquido) each with chart, growth fallback from annual_periods. (15) Per-tab print progress messages. **New mode:** `historical_valuation` — 5Y daily history for 9 metrics via `*_history()` functions. **New metric:** `earnings_yield` (EPS / price = 1 / P/L). Confirmed `_derive_multiples()` outputs already registered in calculations. 1015 tests pass. |
| **v1.7** | 2026-07-31 | **Sync guard wiring.** `__init__.py` now passes `required_sources=["dfp", "itr", "fca", "cotahist", "bridge"]` to `make_route()`. The route() wrapper calls `ensure_fresh()` before each dispatch — if any source is older than 24h (or missing), it triggers force-sync (`force=True`, current-year-only) before running the skill. For CVM sources (dfp/itr/fca): HEAD check before downloading. bridge syncs only the requested ticker. Re-entrancy guard: nested route() calls trigger ensure_fresh() at most once. Escape hatches: `CVM_SKIP_SYNC=1` env var + `route(..., skip_sync=True)` kwarg. Failure path: sync failure proceeds with stale data + error in `result["_sync"]["errors"]`. `REQUIRED_SOURCES` added to MANIFEST. Inherits F7 engine cache automatically. |
| **v1.6** | 2026-07-30 | **Review fixes + skills/_base.py extraction.** Collective LLM review P0 bug fixes (PL zero-value trap, cross-statement empresa_id mismatch). Extracted shared `ModeSpec` + `register_mode` + `make_route` into `skills/_base.py` — all 11 skills now use the same modular pattern. `make_route()` includes sync guard + re-entrancy protection. |
| **v1.5** | 2026-07-29 | **6-tab dashboard reorg with sub-tabs + charts + collapsibles.** `dashboard.py` + `report.py` rewritten to produce 6 tabs: Overview (KPI cards + Key Metrics table + Price Details collapsible), Multiples (top-10 multiples table + bar chart + Less Common Multiples collapsible), Per-share (table + bar chart), Profitability (ratio_grid), Liquidity & Leverage (ratio_grid + Detailed Leverage collapsible), Efficiency & Growth (efficiency table + growth table + growth bar chart). `ratios()` called ONCE + passed to every tab builder. Each tab independently try/except-wrapped. Added `_derive_multiples()` + `_derive_per_share()` + `_derive_detailed_leverage()` helpers. |
| **v1.4** | 2026-07-29 | **File structure split + dashboard mode.** `valuation.py` (528 lines) split into standard modular structure: `_registry.py` + `modes/` (3 files: ratios, summary, dashboard) + `fetchers.py` (price fetching) + `helpers.py` + `report.py`. NEW `dashboard` mode added — 5-tab multi-tab dashboard (Overview/Multiples/Profitability/Liquidity & Leverage/Efficiency & Growth). Same auto-discovery pattern as financials. |
| **v1.3** | 2026-07-29 | **Registry-driven ratios.** `ratios()` now uses `compute_all_ratios()` instead of 25 hardcoded metric imports. All 37 calculations metrics auto-discovered. Portuguese backward-compat aliases preserved (margem_bruta, divida_pl, etc.). Removed `headline_v13_metrics` from `summary()` (all metrics already in `ratios()`). |
| **v1.2** | 2026-07-29 | **Wired 15 v1.3 calculations metrics into `ratios()` + `summary()`.** The calculations skill's v1.3 P2 sprint added 15 new metrics (EV multiples, liquidity, margins, capital structure, growth, coverage, turnover, price/tangible book) but the valuation skill did not surface them. Added 15 metric imports at module top, grouped by family, in a `[v1.4-valuation]` block. Extended `ratios()` with a `v13_new_metrics` loop using the existing `_safe_call(fn, ticker, today)` pattern (FileNotFoundError in one metric returns None without poisoning the rest). Extended `summary()` with a `headline_v13_metrics` block surfacing the 10 most important new metrics (EV/Sales, EV/FCF, Quick Ratio, Cash Ratio, OCF Margin, FCF Margin, Interest Coverage, Cash Flow to Debt, Sustainable Growth, P/Tangible Book) at the top level for quick scanning. New metric keys added to `ratios()` dict: `ev_sales`, `ev_fcf`, `cash_ratio`, `quick_ratio`, `ocf_margin`, `fcf_margin`, `working_capital`, `cash_flow_to_debt`, `retention_ratio`, `sustainable_growth`, `interest_coverage`, `inventory_turnover`, `receivables_turnover`, `fixed_asset_turnover`, `price_to_tangible_book`. All existing ratio keys preserved (Phase 2B 10 metrics + market-cap-derived ratios + snapshot fields). 33 metric keys in `ratios()` total (10 pre-v1.2 + 8 Phase 2B fundamentals + 15 v1.3 new). |
| v1.1 | 2026-07-26 | **Phase 2B+C: Refactored to use calculations engines.** Replaced _get_financials_ttm() (87 lines) + _get_shares_outstanding() (87 lines) with calculations engine calls. Added 8 new fundamental ratios from calculations: ROE, ROA, Gross Margin, Operating Margin, Net Margin, Debt/Equity, Asset Turnover, Current Ratio. ROIC upgraded to use actual tax (not 34% approximation). Graham Number delegated to calculations metric. Kept _get_price() with brapi+investsite fallback. Tests split into 3 files + conftest. 619 -> 495 lines. |
| v1.0.14 | 2026-07-25 | **ROIC + Graham number + TTM valuation + data freshness.** (1) ROIC = NOPAT / Invested Capital (34% tax rate, approximate — flagged via roic_tax_rate). (2) Graham number = sqrt(22.5 × EPS × VPA), only when EPS > 0 and VPA > 0. (3) TTM valuation: _get_financials_ttm() calls financials.quarterly() and uses the TTM summary. Falls back to financials.annual() when TTM key metrics are None (one quarter missing). (4) Data freshness: new skills/cvm/_freshness.py helper returns last-sync timestamps for all CVM/B3 databases. valuation.ratios() now includes data_freshness field. (5) Valuation adapter updated: ROIC + Graham added to indicator table + KPI strip. TTM labels on financial values. |
| v1.0.13 | 2026-07-25 | **Back-calculate market_cap from investsite P/L.** investsite does not expose market cap as a standalone value. Fix: when use_investsite_ratios is True, back-calculate market_cap = investsite_P/L × lucro_liquido. |
| v1.0.12 | 2026-07-25 | **investsite market_cap exact key match + list handling.** |
| v1.0.9 | 2026-07-25 | **UNIT ticker fix.** Market-cap-based ratios (P/L = market_cap / lucro_liquido). |
| v1.0.8 | 2026-07-24 | **Collective LLM review fixes.** Calls financials skill internally. Added PSR, EV/EBITDA, P/FCF, DPA. |

---

## 🔄 In Progress / Next Up

(See [ROADMAP.md](ROADMAP.md) for the full backlog. Highlights:)

- **D1 — Per-statement report adapters** (BPA / BPP / DRE / DFC / DVA or a generic statement adapter) — needed to fully populate the Per-share tab's APA / PPA / RBPA metrics.
- **D2 — Additional calculation metrics** — ROI, COE/CAPM, CAGR, Earnings Yield, + promote `_derive_multiples()` outputs (P/EBITDA, EV/EBIT, P/EV, P/CG, P/DB) to registered metrics.
- **D3 — Additional cash flow metrics** — FCT (Total Cash Flow), FCL (= FCO − CAPEX), Saldo Inicial/Final (cash balance start/end).
- **D4 — New data sources** — B3 index participation (IBOV/SMALL), Beta (5Y), options data (Call/Put, PM, ratio), price volatility windows, annual returns history, macro indicators (Selic/CDI/IPCA/IGP-M via BCB SGS), Dollar/Euro rates.
- **D5 — Dashboard enhancements** — sub-tabs within tabs, price/margin/growth trend charts, collapsible sections for detailed metrics, Statements tab (mirror financials v1.12 Balanço pattern), Peer Comparison tab.
- **Real tax rate for ROIC** — currently uses flat 34% (IRPJ + CSLL). Could derive actual rate from DRE IR+CSLL accounts.

---

## 🚫 Deferred / Out of Scope

- **TIR (IRR)** — not feasible from CVM data. Requires cash flow timing.
- **Sector benchmarks** — ✅ Done via `screener` skill.
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.

---

*Last updated: 2026-08-02 (v1.8). See [CHANGELOG.md](CHANGELOG.md) for version history.
