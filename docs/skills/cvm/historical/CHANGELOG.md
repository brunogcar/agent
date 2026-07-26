<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: pe_history (daily P/L series), ratio_history (any metric), summary (current vs averages + percentile). TTM earnings engine (DFP + ITR derivation). Price engine (COTAHIST). Shares engine (FRE). P/L metric. 2 report adapters. 16 tests. Data range: 2012-present. |

---

## 🔄 Roadmap — Future Metrics

### Adding new metrics (follow the pattern in metrics/pe.py):

| Metric | Formula | Engines needed | Status |
|--------|---------|----------------|--------|
| P/L (pe) | price / (TTM earnings / shares) | price + earnings + shares | ✅ v1.0 |
| P/VPA (pvpa) | price / (PL / shares) | price + balance_sheet + shares | 🔜 Stub |
| EV/EBITDA (ev_ebitda) | (price×shares + debt - cash) / TTM EBITDA | price + earnings + balance_sheet + shares | 🔜 Stub |
| PSR (psr) | price / (TTM revenue / shares) | price + revenue + shares | 🔜 Future |
| Dividend Yield | DPA / price | dividends + price | 🔜 Future |

### Adding new engines (for future metrics):

| Engine | Data source | What it provides | Status |
|--------|------------|------------------|--------|
| price | COTAHIST | Daily close prices | ✅ v1.0 |
| earnings | DFP + ITR | TTM earnings at any date | ✅ v1.0 |
| shares | FRE | Shares outstanding at any date | ✅ v1.0 |
| balance_sheet | DFP + ITR | PL, debt, cash at any date (TTM for flows, snapshot for balances) | 🔜 Needed for pvpa, ev_ebitda |
| revenue | DFP + ITR | TTM revenue at any date | 🔜 Needed for PSR |
| dividends | B3 + DFP | DPA at any date | 🔜 Needed for Div Yield |

### Backtest skill (future):

The engines/ are designed for reuse by `skills/cvm/backtest/`:
- `price_at(ticker, date)` — entry/exit prices
- `pe_at(ticker, date)` — strategy signals ("buy when P/L < 5")
- `ttm_earnings_at(ticker, date)` — fundamental filters

A future backtest skill would:
1. Import historical engines to generate signals
2. Import price engine to compute returns
3. Run a strategy over a date range
4. Return performance metrics (CAGR, Sharpe, max drawdown)

---

## 🚫 Deferred / Out of Scope

- **Intraday data** — COTAHIST is daily. Intraday needs B3 API trades.
- **International stocks** — CVM/B3 data only. US stocks need a different data source.
- **Options pricing** — COTAHIST has options data (BDI filter excludes it). Would need separate handling.

---

*Last updated: 2026-07-25 (v1.0).*
