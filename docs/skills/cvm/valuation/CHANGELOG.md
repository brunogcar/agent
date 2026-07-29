<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.2** | 2026-07-29 | **Wired 15 v1.3 calculations metrics into `ratios()` + `summary()`.** The calculations skill's v1.3 P2 sprint added 15 new metrics (EV multiples, liquidity, margins, capital structure, growth, coverage, turnover, price/tangible book) but the valuation skill did not surface them. Added 15 metric imports at module top, grouped by family, in a `[v1.4-valuation]` block. Extended `ratios()` with a `v13_new_metrics` loop using the existing `_safe_call(fn, ticker, today)` pattern (FileNotFoundError in one metric returns None without poisoning the rest). Extended `summary()` with a `headline_v13_metrics` block surfacing the 10 most important new metrics (EV/Sales, EV/FCF, Quick Ratio, Cash Ratio, OCF Margin, FCF Margin, Interest Coverage, Cash Flow to Debt, Sustainable Growth, P/Tangible Book) at the top level for quick scanning. New metric keys added to `ratios()` dict: `ev_sales`, `ev_fcf`, `cash_ratio`, `quick_ratio`, `ocf_margin`, `fcf_margin`, `working_capital`, `cash_flow_to_debt`, `retention_ratio`, `sustainable_growth`, `interest_coverage`, `inventory_turnover`, `receivables_turnover`, `fixed_asset_turnover`, `price_to_tangible_book`. All existing ratio keys preserved (Phase 2B 10 metrics + market-cap-derived ratios + snapshot fields). 33 metric keys in `ratios()` total (10 pre-v1.2 + 8 Phase 2B fundamentals + 15 v1.3 new). |
| v1.1 | 2026-07-26 | **Phase 2B+C: Refactored to use calculations engines.** Replaced _get_financials_ttm() (87 lines) + _get_shares_outstanding() (87 lines) with calculations engine calls. Added 8 new fundamental ratios from calculations: ROE, ROA, Gross Margin, Operating Margin, Net Margin, Debt/Equity, Asset Turnover, Current Ratio. ROIC upgraded to use actual tax (not 34% approximation). Graham Number delegated to calculations metric. Kept _get_price() with brapi+investsite fallback. Tests split into 3 files + conftest. 619 -> 495 lines. |
| v1.0.14 | 2026-07-25 | **ROIC + Graham number + TTM valuation + data freshness.** (1) ROIC = NOPAT / Invested Capital (34% tax rate, approximate — flagged via roic_tax_rate). (2) Graham number = sqrt(22.5 × EPS × VPA), only when EPS > 0 and VPA > 0. (3) TTM valuation: _get_financials_ttm() calls financials.quarterly() and uses the TTM summary. Falls back to financials.annual() when TTM key metrics are None (one quarter missing). (4) Data freshness: new skills/cvm/_freshness.py helper returns last-sync timestamps for all CVM/B3 databases. valuation.ratios() now includes data_freshness field. (5) Valuation adapter updated: ROIC + Graham added to indicator table + KPI strip. TTM labels on financial values. |
| v1.0.13 | 2026-07-25 | **Back-calculate market_cap from investsite P/L.** investsite does not expose market cap as a standalone value. Fix: when use_investsite_ratios is True, back-calculate market_cap = investsite_P/L × lucro_liquido. |
| v1.0.12 | 2026-07-25 | **investsite market_cap exact key match + list handling.** |
| v1.0.9 | 2026-07-25 | **UNIT ticker fix.** Market-cap-based ratios (P/L = market_cap / lucro_liquido). |
| v1.0.8 | 2026-07-24 | **Collective LLM review fixes.** Calls financials skill internally. Added PSR, EV/EBITDA, P/FCF, DPA. |

---

## 🔄 In Progress / Next Up

- **Real tax rate for ROIC** — currently uses flat 34% (IRPJ + CSLL). Could derive actual rate from DRE IR+CSLL accounts.
- **CAPEX from DFC** — currently FCI is the proxy for P/FCF. Real CAPEX needs wildcard/description match.
- **COTAHIST historical P/L** — P/L over time (needs COTAHIST historical prices + historical financials).

---

## 🚫 Deferred / Out of Scope

- **TIR (IRR)** — not feasible from CVM data. Requires cash flow timing.
- **Sector benchmarks** — ✅ Done via `screener` skill.
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.

---

*Last updated: 2026-07-29 (v1.2).*
