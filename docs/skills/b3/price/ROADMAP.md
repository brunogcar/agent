<- Back to [PRICE Overview](../PRICE.md)

# 🗺️ PRICE Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | P1 — RSI + MACD | Momentum oscillators on a new "Momentum" subtab |
| P2 | P2 — Dividend-adjusted returns | True total return (price + dividends + splits) |
| P2 | P3 — Intraday data | Real-time + intraday OHLCV via brapi or B3 market data |
| P3 | P4 — Options chain | Put/call ratio + IV smile for tickers with listed options |
| P3 | P5 — Multi-ticker compare | Side-by-side price + return comparison (mirror b3/index compare) |
| P3 | P6 — Pattern recognition | Auto-detect head-and-shoulders, double tops, triangles |
| Done | v1.0 launch | 2 modes (dashboard, quote) + 5-tab dashboard + candlestick support |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### P1 — RSI + MACD

**Priority:** P2
**Source:** Quant analysis need

Two classic momentum oscillators:
- **RSI (Relative Strength Index, 14-day)** — overbought (>70) / oversold (<30) zones.
- **MACD (Moving Average Convergence Divergence, 12/26/9)** — signal-line crossovers + histogram.

**Implementation:**
1. Add `compute_rsi(closes, period=14)` and `compute_macd(closes, fast=12, slow=26, signal=9)` to `engines.py`.
2. Add a new "Momentum" subtab to the Volatilidade tab (or a new 6th tab).
3. Build a 3-panel chart: RSI line with 30/70 horizontal lines, MACD line + signal line + histogram.

**Blocker:** None. Pure-Python computation, no new data source.

### P2 — Dividend-adjusted returns

**Priority:** P2
**Source:** Portfolio performance analysis

Current cumulative return is **price-only** — it ignores dividends and splits.
A stock that paid 10% in dividends + had 0% price change would show 0% return,
understating the true total return by 10%.

**Implementation:**
1. Fetch B3 dividends (`data_sources/b3/dividends`) for the ticker + date range.
2. Fetch corporate events (splits, inplitos) from B3 corporate actions catalog.
3. Compute the adjusted close series: `adj_close[t] = close[t] * adj_factor[t]`
   where `adj_factor` accounts for splits + reinvested dividends.
4. Use `adj_close` instead of `close` in `compute_cumulative_returns` + `compute_drawdowns`.
5. Surface both raw + adjusted return in the Retornos tab KPI table.

**Blocker:** Requires `b3_dividends` source synced for the ticker. Add to `REQUIRED_SOURCES`.

### P3 — Intraday data

**Priority:** P2
**Source:** Trading use case

COTAHIST is end-of-day only. Intraday tick or 1-minute bars would enable:
- Intraday momentum (15-min RSI, VWAP).
- Better entry/exit timing signals.
- Real-time charting (vs current T+1 data).

**Implementation:**
1. Add a new `intraday` mode that polls brapi (15-min delayed) or a paid B3 feed.
2. Cache ticks in a separate `intraday.db` (rolling 30-day window).
3. Reuse the existing candlestick chart but with 1-min / 5-min / 15-min granularity selector.

**Blocker:** brapi free tier is 15-min delayed + rate-limited. A real-time feed
requires a paid B3 market data subscription.

### P4 — Options chain

**Priority:** P3
**Source:** Derivatives traders

For tickers with listed options (PETR4, VALE3, ITUB4, etc.), surface:
- Put/call ratio (sentiment indicator).
- Implied volatility smile (near-the-money vs far-OTM IV).
- Open interest by strike (support/resistance levels).

**Implementation:**
1. New `options` mode — fetch B3 derivatives data (COTAHIST already includes
   options trades, filtered out by `BDI_FILTER` in catalog.py).
2. Re-enable BDI codes for options in a separate query path.
3. Surface as a new "Opções" tab in the dashboard.

**Blocker:** Options data is in the same COTAHIST ZIP but currently filtered
out during sync. Need a separate query path (not a re-sync).

### P5 — Multi-ticker compare

**Priority:** P3
**Source:** Portfolio management

Side-by-side comparison of 2-5 tickers:
- Normalized price chart (all starting at 100).
- Return table (1M / 3M / 6M / 1Y / 5Y / YTD).
- Volatility comparison (20D / 60D / 252D).
- Correlation matrix (rolling 60D Pearson).

**Implementation:**
1. New `compare` mode mirroring `b3/index/modes/compare.py`.
2. Reuse engine functions (compute_returns, compute_volatility) per ticker.
3. Add a correlation engine: `compute_correlation(returns_a, returns_b, window=60)`.

**Blocker:** None technical. The candlestick chart stays single-ticker — compare
uses line charts only.

### P6 — Pattern recognition

**Priority:** P3
**Source:** Technical analysis automation

Automatic detection of classical chart patterns:
- Reversal: head-and-shoulders, double tops/bottoms, falling/rising wedge.
- Continuation: flags, pennants, triangles (ascending/descending/symmetric).

**Implementation:**
1. Add `find_patterns(dates, ohlcv)` to `engines.py` (returns list of detected
   patterns with confidence scores).
2. Surface as a new "Padrões" tab with annotated chart + table.
3. Use a simple peak/trough detection algorithm (no ML needed for v1).

**Blocker:** Pattern detection is fuzzy — high false-positive rate. Need a
confidence threshold + user-tunable sensitivity.

---

*Last updated: 2026-08-06 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
