<- Back to [PRICE Overview](../PRICE.md)

# 🗺️ PRICE Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | P3 — Intraday data | Real-time + intraday OHLCV via brapi or B3 market data |
| P3 | P4 — Options chain | Put/call ratio + IV smile for tickers with listed options |
| P3 | P5 — Multi-ticker compare | Side-by-side price + return comparison (mirror b3/index compare) |
| P3 | P6 — Pattern recognition | Auto-detect head-and-shoulders, double tops, triangles |

---

## 📋 Backlog

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

**Status:** The options skill ([b3/options](../OPTIONS.md)) is live as a
separate skill. The price dashboard previously embedded it as a 9th tab
(v1.7) but this was removed in v2.0 — price skill is now price-only.

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

*Last updated: 2026-08-28 (v2.0 — removed completed items, P10/P7/P8/P9/P2 shipped). See [CHANGELOG.md](CHANGELOG.md) for version history.*
