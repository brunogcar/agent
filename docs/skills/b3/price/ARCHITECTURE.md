<- Back to [PRICE Overview](../PRICE.md)

# 🏗️ Architecture — price skill

## Purpose

Single-ticker price analytics from B3 COTAHIST daily OHLCV data. Six tabs:
1. **Cotação** — candlestick + 4 MAs + volume bars + 6 KPIs
2. **Médias Móveis** — SMA20/50/100/200 line chart + crossover table
3. **Volume** — colored volume bars + price overlay + statistics
4. **Indicadores** — RSI + MACD + Stochastic + OBV + signals table  [v1.2]
5. **Retornos** — cumulative return + drawdown + performance summary
6. **Volatilidade** — rolling vol (20D/60D/252D) + Bollinger Bands + KPI

## 🔗 Source Code Reference

```text
skills/b3/price/
├── __init__.py        MANIFEST + route() dispatch (auto-discovery) + REQUIRED_SOURCES=["cotahist"]
├── _registry.py       ModeSpec + register_mode + MODES dict (delegates to skills/_base.py)
├── engines.py         ALL computation: ohlcv_series, latest_quote, compute_sma, compute_returns,
│                      compute_cumulative_returns, compute_drawdowns, compute_volatility,
│                      compute_bollinger_bands, find_ma_crossovers, compute_52w_range,
│                      compute_ema, compute_rsi, compute_macd, compute_stochastic, compute_obv  [v1.2]
├── report/            section builders (pure shape — no computation)
│   ├── __init__.py    re-exports all 7 builders
│   ├── cotacao.py     build_quote_kpis + build_cotacao_sections (candlestick + volume)
│   ├── medias.py      build_medias_sections (SMA chart + crossovers table)
│   ├── volume.py      build_volume_sections (volume bars + price overlay + stats)
│   ├── indicadores.py build_indicadores_sections (RSI + MACD + Stochastic + OBV + signals)  [v1.2]
│   ├── retornos.py    build_retornos_sections (cumulative return + drawdown)
│   └── volatilidade.py build_volatilidade_sections (rolling vol + BB)
└── modes/             one file per mode, auto-discovered via importlib
    ├── __init__.py    minimal package marker
    ├── dashboard.py   @register_mode("dashboard") — 6-tab deep dive (default)
    └── quote.py       @register_mode("quote")     — latest OHLCV snapshot
```

### Test module tree

```text
tests/skills/b3/price/
├── conftest.py        price_env fixture — synthetic cotahist.db (10 PETR4 days)
├── test_dashboard.py  TestDashboardMode (2 tests — error path + 6-tab structure)
└── test_route.py      TestPriceRoute (2 tests — no-mode error + manifest modes)
```

4 tests total (v1.2).

## Data Flow

```
skill(domain="b3", sub_domain="price", mode="dashboard", params='{"ticker":"PETR4"}')
  │
  ▼  ensure_fresh(["cotahist"])  ← route() wrapper, sync guard
  │  1. Check cotahist sync_state.last_synced_at < 24h
  │  2. If stale → call sync(year=current_year) (~30s)
  │
  ▼  dashboard mode (modes/dashboard.py)
  │  1. ohlcv_series("PETR4", date_from=10Y_ago, date_to=today)
  │     → 10 years of OHLCV rows from engines.py
  │  2. Compute MA20/50/100/200 + returns + cum_returns + drawdowns
  │     + vol_20d/60d/252d + Bollinger Bands + MA crossovers (MA20×MA50, MA50×MA200)
  │     + [v1.2] RSI(14) + MACD(12/26/9) + Stochastic(14/3/3) + OBV
  │  3. compute_52w_range + latest_quote (for KPIs)
  │  4. Pass computed arrays to report/ builders (no recomputation in builders)
  │  5. Build 6 tabs: Cotação, Médias Móveis, Volume, Indicadores, Retornos, Volatilidade
  │  6. Return {status, ticker, tabs, kpis, period, crossovers}
  │
  ▼  _auto_generate_html()  ← writes PETR4_price_dashboard.html to workspace/reports/
```

## Engine Design

`engines.py` is the SINGLE home for all computation. Report builders consume
its output and emit section dicts — they do NOT recompute anything. This
separation makes the builders trivially testable (pass in synthetic arrays,
assert the shape of the output dict).

### Engine inventory

| Function | Returns | Notes |
|----------|---------|-------|
| `ohlcv_series(ticker, date_from, date_to)` | `[{date, open, high, low, close, volume, trade_count}]` | Sorted oldest-first; filters market_type=10 (lote padrão) |
| `latest_quote(ticker)` | `{date, open, high, low, close, volume, trade_count}` or None | Most recent close |
| `compute_sma(closes, period)` | `[float \| None]` (same length) | First `period-1` entries are None |
| `compute_returns(closes)` | `[float \| None]` (same length) | First entry None (no prior close) |
| `compute_cumulative_returns(closes)` | `[float \| None]` | Fraction from first valid close |
| `compute_drawdowns(closes)` | `[float \| None]` | Negative fractions (or 0 at peak) |
| `compute_volatility(returns, period)` | `[float \| None]` | Annualized (×√252) rolling stdev |
| `compute_bollinger_bands(closes, period=20, num_std=2.0)` | `(upper, middle, lower)` tuple | Three aligned arrays |
| `find_ma_crossovers(dates, ma_fast, ma_slow)` | `[{date, type, signal, fast, slow}]` | Golden (buy) + Death (sell) signals |
| `compute_52w_range(ticker, today)` | `{high_52w, low_52w}` | 365-day window |
| `compute_ema(closes, period)` | `[float \| None]` | [v1.2] Exponential MA; seeds with SMA, recurses with mult=2/(period+1). MACD dependency |
| `compute_rsi(closes, period=14)` | `[float \| None]` | [v1.2] Wilder's smoothing RSI, 0-100. First `period` entries None |
| `compute_macd(closes, fast=12, slow=26, signal=9)` | `(macd_line, signal_line, histogram)` tuple | [v1.2] 3 aligned arrays |
| `compute_stochastic(highs, lows, closes, k_period=14, d_period=3)` | `(k_line, d_line)` tuple | [v1.2] %K + %D, 0-100 |
| `compute_obv(closes, volumes)` | `[float \| None]` | [v1.2] Cumulative signed volume (OBV[0]=0) |

### Report builder inventory

| Function | Returns | Section types emitted |
|----------|---------|------------------------|
| `build_quote_kpis(quote, prev_close, range_52w)` | `[{type:kpi, label, value, unit, subtitle, delta}]` | 6 KPI cards |
| `build_cotacao_sections(ticker, ohlcv, ma20, ma50, ma100, ma200)` | `[candlestick, chart]` | Candlestick + volume bars |
| `build_medias_sections(ticker, dates, closes, ma20, ma50, ma100, ma200, crossovers)` | `[chart, table]` | SMA line + crossover table |
| `build_volume_sections(ticker, dates, volumes, closes, opens, vol_ma20=None)` | `[chart, table]` | Volume bars + price overlay + stats |
| `build_indicadores_sections(ticker, dates, closes, highs, lows, volumes, rsi, macd, signal, hist, k, d, obv)` | `[chart, chart, chart, chart, chart, table]` | [v1.2] Price reference + RSI + MACD + Stochastic + OBV (4 collapsible) + signals |
| `build_retornos_sections(ticker, dates, closes, cum_returns, drawdowns)` | `[chart, chart, table]` | Cumulative + drawdown + KPIs |
| `build_volatilidade_sections(ticker, dates, closes, vol_20d, vol_60d, vol_252d, bb_*)` | `[chart, chart, table]` | Rolling vol + BB + KPIs |

## Candlestick Chart Shape

[v1.2] The candlestick is rendered by the vanilla `_renderOHLCChart`
helper in `dashboard.html` (flagged via `chart_data._ohlc = True`). The
body is drawn as floating-bar datasets `[min(o,c), max(o,c)]`; wicks are
rendered via an inline Chart.js plugin that reads from `chart._ohlc`.

The `chartjs-chart-financial` plugin was used in the initial v1.0 draft
but removed because it forced a `time` x-scale that required a date
adapter (rendered blank without it). The CDN tag + the `type: "candlestick"`
macro branch were removed in v1.1 as dead code.

Each candle is an object `{"o": float, "h": float, "l": float, "c": float}`
stored in `chart_data._ohlc_data`. The chart_data also includes 4 line
datasets (MA20/50/100/200) as overlays. The dual-axis (price left,
volume right) is configured via `scales.y` + `scales.y1`.

## Range Selector

The price_range_selector renders 7 buttons: Tudo / 10A / 5A / 1A / 6M / 3M / 1M.
`filterPriceChart(btn, canvasId, range)` JS in `dashboard.html` filters the
chart's dataset client-side based on the selected range.

For candlestick + multi-dataset charts (e.g., MA overlays), the
`price_full_datasets` field carries the auxiliary series so they can be
filtered alongside the main price series.

## Modes

| Mode | Default | Source | Returns |
|------|---------|--------|---------|
| `dashboard` | 10Y window | COTAHIST | 6-tab dashboard payload (Cotação / Médias / Volume / Indicadores / Retornos / Volatilidade) + 6 KPIs |
| `quote` | — | COTAHIST | Latest OHLCV + 52-week range + 6 KPI cards |

## Sync Guard (v1.0)

`REQUIRED_SOURCES = ["cotahist"]` wired via `make_route()`.

- `route()` calls `ensure_fresh()` before each dispatch — checks `cotahist.sync_state.last_synced_at`.
- If stale (> 24h) or missing, triggers `sync(year=current_year, force=True)`.
- Re-entrancy guard: nested `route()` calls (none currently, but reserved for future composable modes) trigger `ensure_fresh()` at most once.
- Escape hatches: `CVM_SKIP_SYNC=1` env var (set in conftest for tests) + `route(..., skip_sync=True)` kwarg.

---

*Last updated: 2026-08-13 (v1.2 — Indicadores tab + 5 momentum oscillator engines + candlestick doc fix). See [CHANGELOG.md](CHANGELOG.md) for version history.*
