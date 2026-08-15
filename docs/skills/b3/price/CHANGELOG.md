<- Back to [PRICE Overview](../PRICE.md)

# 🗺️ Changelog — price skill

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-08-13 | **Retornos dual-axis removal + y-axis unit fix + dead-code cleanup.** (1) Removed the dual-axis price overlay (right axis) from the Retornos tab's cumulative-return + drawdown charts — they now show ONLY the return/drawdown series on a single left axis (cleaner reading; the Cotacao tab's Volume Diário chart keeps its dual-axis price overlay by design). (2) Fixed y-axis unit mismatch — chart data values were raw fractions (0.15) but the axis title said "(%)", so the displayed values didn't match the title. Now the chart data is multiplied by 100 (0.15 → 15.0) so the axis matches. The KPI table is unaffected (still uses `fmt_pct` on raw fractions). (3) Removed the dead `chartjs-chart-financial` CDN script tag from `dashboard.html` — the candlestick is rendered by the vanilla `_renderOHLCChart` helper (flagged via `chart_data._ohlc`), NOT the chartjs-chart-financial plugin (which was replaced because it forced a `time` x-scale that rendered blank without a date adapter). (4) Removed the dead `type: "candlestick"` macro branch from `macros.html` — no section emits this type; OHLC charts use `type: "chart"` with `_ohlc: True`. |
| v1.0 | 2026-08-06 | **Initial implementation.** 2 modes: dashboard (5-tab: Cotação / Médias Móveis / Volume / Retornos / Volatilidade) + quote (latest OHLCV + 52w range). Modular `_registry.py` + `modes/` + `report/` pattern (delegates to `skills/_base.py`). Engines pre-built with 9 functions (ohlcv_series, latest_quote, SMA, returns, cumulative_returns, drawdowns, volatility, Bollinger Bands, MA crossovers, 52w range). Candlestick chart rendered via vanilla Chart.js `_renderOHLCChart` helper (flagged via `chart_data._ohlc`) — NOT the chartjs-chart-financial plugin (was removed during v1.0 dev because it forced a `time` x-scale that rendered blank). Range selector expanded to 7 buttons (Tudo/10A/5A/1A/6M/3M/1M). Sync guard wired via `required_sources=["cotahist"]` + `make_route()`. 4 tests. Read-only over `data_sources/b3/cotahist`. |

---

## 🔄 In Progress / Next Up

- **RSI + MACD** — momentum oscillators. RSI (14) overbought/oversold zones + MACD (12/26/9) crossovers. Would extend the Volatilidade tab with a "Momentum" subtab.
- **Intraday data** — currently only end-of-day OHLCV. Intraday would require a streaming/polling API (brapi or B3 market data feed).
- **Dividend-adjusted returns** — current returns are price-only. Adjusting for dividends + splits would give true total return (needs B3 dividends + corporate events data).
- **Options chain** — for tickers with listed options (PETR4, VALE3, etc.), surface the put/call ratio + implied volatility smile.

---

## 🚫 Deferred / Out of Scope

- **Multi-ticker comparison** — belongs in a future `compare` mode (mirror of `b3/index` compare). The candlestick chart is single-ticker by design.
- **Backtesting** — running a strategy on the historical price series belongs in `skills/cvm/backtest`, not here. The price skill only surfaces data; it doesn't simulate trades.
- **Technical pattern recognition** — automatic detection of head-and-shoulders, double tops, triangles, etc. would belong in a future `patterns` mode (or a separate `technical_analysis` skill).

---

*Last updated: 2026-08-13 (v1.1).*
