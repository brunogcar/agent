<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-07-26 | **PL engine + VPA metric + engine/metric separation.** New `engines/pl.py` (Patrimônio Líquido snapshot from DFP+ITR BPP 2.03). New `metrics/vpa.py` (P/VPA = price / (PL / shares)). New `vpa_history` mode. `summary` + `ratio_history` made metric-aware via `_metric_dispatch()`. New `historical_vpa_chart` adapter. `historical_summary` adapter made metric-aware (renders PL row for vpa, TTM Earnings row for pe). Renamed `pvpa.py` → `vpa.py` (engine produces PL, metric computes VPA — clear separation). Documented engine vs metric pattern in ARCHITECTURE + INSTRUCTIONS. 38 historical tests + 9 adapter tests. |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: pe_history (daily P/L series), ratio_history (any metric), summary (current vs averages + percentile). TTM earnings engine (DFP + ITR derivation). Price engine (COTAHIST). Shares engine (FRE + investsite fallback). P/L metric. 2 report adapters. 16 tests. Data range: 2012-present. |

---

### ⚠️ Breaking Changes

#### v1.1 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/pvpa.py` renamed → `metrics/vpa.py` | Old import path no longer exists. | `from skills.cvm.historical.metrics.pvpa import ...` → `from skills.cvm.historical.metrics.vpa import ...`. Delete old `pvpa.py` file. |
| `ratio_history(metric="pvpa")` removed | Was a stub returning `not_implemented`. | Use `metric="vpa"` instead — now fully implemented. |
| New mode `vpa_history` | None (additive). | No migration. |
| `summary()` now metric-aware | `current` block includes `pl` + `shares` (not `ttm_earnings`) when `metric="vpa"`. | Update any caller that hardcodes `current["ttm_earnings"]` — check `result["metric"]` first. |
| `historical_summary` adapter now metric-aware | Renders PL row for vpa, TTM Earnings row for pe. | No migration — reads `result["metric"]` automatically. |

---

## 🔄 Roadmap — Future Metrics

### Adding new metrics (follow the engine/metric pattern in ARCHITECTURE.md):

| Metric | Formula | Engines needed | Status |
|--------|---------|----------------|--------|
| P/L (pe) | price / (TTM earnings / shares) | price + earnings + shares | ✅ v1.0 |
| P/VPA (vpa) | price / (PL / shares) | price + pl + shares | ✅ v1.1 |
| EV/EBITDA (ev_ebitda) | (price×shares + debt - cash) / TTM EBITDA | price + earnings + balance_sheet + shares | 🔜 Stub |
| PSR (psr) | price / (TTM revenue / shares) | price + revenue + shares | 🔜 Future |
| Dividend Yield | DPA / price | dividends + price | 🔜 Future |

### Adding new engines (for future metrics):

| Engine | Data source | What it provides | Status |
|--------|------------|------------------|--------|
| price | COTAHIST | Daily close prices | ✅ v1.0 |
| earnings | DFP + ITR | TTM earnings at any date | ✅ v1.0 |
| shares | FRE + investsite | Shares outstanding at any date | ✅ v1.0 |
| pl | DFP + ITR | Patrimônio Líquido snapshot at any date | ✅ v1.1 |
| balance_sheet | DFP + ITR | debt, cash, EBIT, D&A at any date (TTM for flows, snapshot for balances) | 🔜 Needed for ev_ebitda |
| revenue | DFP + ITR | TTM revenue at any date (codigo 3.01) | 🔜 Needed for PSR |
| dividends | B3 + DFP | DPA at any date | 🔜 Needed for Div Yield |

### Backtest skill (future):

The engines/ and metrics/ are designed for reuse by `skills/cvm/backtest/`:
- `price_at(ticker, date)` — entry/exit prices
- `pe_at(ticker, date)` — strategy signals ("buy when P/L < 5")
- `vpa_at(ticker, date)` — strategy signals ("buy when P/VPA < 1.0")
- `ttm_earnings_at(ticker, date)` — fundamental filters
- `pl_at(ticker, date)` — fundamental filters

A future backtest skill would:
1. Import historical engines + metrics to generate signals
2. Import price engine to compute returns
3. Run a strategy over a date range
4. Return performance metrics (CAGR, Sharpe, max drawdown)

---

## 🚫 Deferred / Out of Scope

- **Intraday data** — COTAHIST is daily. Intraday needs B3 API trades.
- **International stocks** — CVM/B3 data only. US stocks need a different data source.
- **Options pricing** — COTAHIST has options data (BDI filter excludes it). Would need separate handling.
- **Standalone quarter computation** — ITR is cumulative (Jan→period end). Standalone T2/T3/T4 derivation belongs in the financials skill, not here.

---

*Last updated: 2026-07-26 (v1.1 — PL engine + VPA metric).*
