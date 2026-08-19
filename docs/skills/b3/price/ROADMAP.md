<- Back to [PRICE Overview](../PRICE.md)

# 🗺️ PRICE Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | P3 — Intraday data | Real-time + intraday OHLCV via brapi or B3 market data |
| P3 | P4 — Options chain | Put/call ratio + IV smile for tickers with listed options |
| P3 | P5 — Multi-ticker compare | Side-by-side price + return comparison (mirror b3/index compare) |
| P3 | P6 — Pattern recognition | Auto-detect head-and-shoulders, double tops, triangles |
| ✅ | ~~P10 — Opções tab (cross-skill)~~ | **Shipped 2026-09-05 (v1.7)** — 9th "Opções" tab embeds the Cadeia de Opções (calls + puts + legend) from the [b3/options](../OPTIONS.md) skill. Cross-skill integration: `_build_options_tab(ticker)` calls `skills.b3.options.modes.dashboard.dashboard(underlying=ticker)` and extracts just the Cadeia de Opções tab sections. Graceful skip if the options skill import fails or the underlying has no listed options. |
| ✅ | ~~P7 — ADX / CCI / Williams %R~~ | **Shipped 2026-08-22 (v1.6)** — 3 trend/cyclical indicators added to `engines.py` (`compute_adx`, `compute_cci`, `compute_williams_r`) + 3 collapsible chart sections in the Indicadores tab + 3 rows in the signals table + 3 signal classifiers. |
| ✅ | ~~P8 — Bid-ask spread analysis~~ | **Shipped 2026-08-22 (v1.6)** — new 8th "Bid-Ask Spread" tab (group: Liquidez) with 4 sections: spread absoluto + spread percentual + bid/ask/close + liquidez KPI table. `ohlcv_series` SELECT extended with `best_bid, best_ask`. New `compute_bid_ask_spread` + `compute_spread_pct` engine functions + new `report/spread.py` builder. |
| ✅ | ~~P9 — Options skill (new)~~ | **Shipped 2026-08-18** as the separate [b3/options](../OPTIONS.md) skill (v1.0). Reads from `data_sources/b3/cotahist_derivatives` (the `cotahist_derivatives` table, populated during the standard COTAHIST sync). See [../options/CHANGELOG.md](../options/CHANGELOG.md). |

> **Note:** Recently completed items (Opções tab cross-skill in v1.7, ADX/CCI/Williams %R + Bid-Ask Spread tab in v1.6, Fibonacci + dividend-adjusted returns, RSI+MACD+Stochastic+OBV, v1.0 launch, v1.1 cleanup) are in [CHANGELOG.md](CHANGELOG.md). The ROADMAP only tracks backlog + deferred items.

---

## 📋 Backlog

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

**Status update (2026-08-18):** the heavy lifting (options chain data +
put/call ratio + volume-by-strike analytics) has shipped as the separate
[b3/options](../OPTIONS.md) skill, reading from the new
`cotahist_derivatives` table. The remaining scope for the price skill is
the **cross-skill integration** — embedding the options Cadeia de Opções
tab as a new "Opções" tab here. Tracked as P10 below.

**Blocker:** None — the options skill + `cotahist_derivatives` table are
live. Just needs the price dashboard wiring + a graceful-skip when the
underlying has no listed options.

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

### P10 — Opções tab (cross-skill integration with b3/options) — DONE in v1.7

**Priority:** P3
**Source:** Cross-skill integration

**Shipped 2026-09-05 (v1.7).** Added a 9th "Opções" tab (group: Derivativos) to the price dashboard that calls the [b3/options](../OPTIONS.md) skill's `dashboard` mode and embeds just the Cadeia de Opções tab sections (calls table + puts table + legend). Skips the P/C ratio, Volume por Strike, Exercicios, and IV tabs to keep the price dashboard compact.

With the [b3/options](../OPTIONS.md) skill now live (v1.0, 2026-08-18), the
price dashboard could embed a new "Opções" tab that calls the options
skill's `dashboard` mode and renders the Cadeia de Opções table inline.
Currently a user has to call the options skill separately.

**Implementation (shipped):**
1. Added `from skills.b3.options.modes.dashboard import dashboard as _options_dashboard`
   wrapped in try/except (`_OPTIONS_AVAILABLE` flag) so a missing options
   skill or circular-import issue doesn't break the price dashboard.
2. New helper `_build_options_tab(ticker)` calls `_options_dashboard(underlying=ticker)`,
   extracts the "Cadeia de Opções" tab sections, and returns them. Graceful
   fallback to a "Sem opções disponíveis para este ticker" text section if
   the call fails or returns no Cadeia tab.
3. Added `{"name": "Opções", "group": "Derivativos", "sections": options_sections}`
   as the 9th tab.
4. Updated `@register_mode` description to mention 9 tabs.

No new sync guard needed — the options skill's `REQUIRED_SOURCES=["cotahist",
"sgs"]` is a subset of the price skill's `REQUIRED_SOURCES=["cotahist",
"b3_dividends"]`.

---

*Last updated: 2026-09-05 (v1.7 — P10 shipped). See [CHANGELOG.md](CHANGELOG.md) for version history.*
