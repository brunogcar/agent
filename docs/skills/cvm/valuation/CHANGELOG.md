<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.8 | 2026-07-24 | **Collective LLM review fixes.** (1) Valuation now calls financials skill internally (`_get_financials()`) instead of duplicating DFP code list — gets EBITDA, margins, ROE/ROA for free. (2) Added PSR, EV/EBITDA, P/FCF, DPA, Dívida Líq/EBITDA. (3) Fixed brapi price_date (was "", now uses today). (4) Fixed shares source mislabel (capital_social fallback now correctly labeled). (5) Fixed stale docstring. (6) Negative PL guard for P/VPA (returns None when PL ≤ 0). |
| v1.0 | 2026-07-24 | **Initial implementation.** 2 modes: ratios (P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap) + summary. Price from brapi (primary) or investsite (fallback) or b3 trades.db (last resort). Shares from FRE (primary) or investsite (fallback). Auto-sync bridge for new tickers. |

---

## 🔄 In Progress / Next Up

- **ROIC** — NOPAT / Invested Capital = EBIT × (1 - tax_rate) / (PL + Dívida - Caixa). Needs tax rate (derive from DRE IR+CSLL, or use 34% as default). Flag as approximate.
- **CAPEX** — from DFC investing activities. Not a single fixed code — varies by company. Needs wildcard/description match approach like EBIT.
- **TTM ratios** — Currently uses latest annual DFP. TTM (trailing twelve months) would be more current. Combines ITR quarterly + DFP annual. Critical for seasonal businesses.
- **COTAHIST as historical price source** — for P/L over time, backtesting, charts. COTAHIST is official + instant (local).
- **Graham number** — sqrt(22.5 × EPS × VPA). Simple value investing formula.

---

## 🚫 Deferred / Out of Scope

- **TIR (IRR)** — not feasible from CVM data. Requires cash flow timing (dates of each cash flow), which annual/quarterly filings don't provide. Would need a separate DCF calculator with user-supplied assumptions.
- **Sector benchmarks** — aggregate financials across companies for median P/L, ROE, etc. Separate skill (e.g., `skills/cvm/screener`).
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling for a local-first agent without paid B3 feeds.

---

*Last updated: 2026-07-24 (v1.0.8).*
