<- Back to [PRICE Overview](../PRICE.md)

# 🏗️ Architecture — price skill

## Purpose

Single-ticker price analytics from B3 COTAHIST daily OHLCV data. Five tabs:
1. **Cotação** — candlestick + 4 MAs + volume bars + 6 KPIs
2. **Médias Móveis** — SMA20/50/100/200 line chart + crossover table
3. **Volume** — colored volume bars + 20-day volume MA + statistics
4. **Retornos** — cumulative return + drawdown + performance summary
5. **Volatilidade** — rolling vol (20D/60D/252D) + Bollinger Bands + KPI

## 🔗 Source Code Reference

```text
skills/b3/price/
├── __init__.py        MANIFEST + route() dispatch (auto-discovery) + REQUIRED_SOURCES=["cotahist"]
├── _registry.py       ModeSpec + register_mode + MODES dict (delegates to skills/_base.py)
├── engines.py         ALL computation: ohlcv_series, latest_quote, compute_sma, compute_returns,
│                      compute_cumulative_returns, compute_drawdowns, compute_volatility,
│                      compute_bollinger_bands, find_ma_crossovers, compute_52w_range
├── report/            section builders (pure shape — no computation)
│   ├── __init__.py    re-exports all 6 builders
│   ├── cotacao.py     build_quote_kpis + build_cotacao_sections (candlestick + volume)
│   ├── medias.py      build_medias_sections (SMA chart + crossovers table)
│   ├── volume.py      build_volume_sections (volume bars + MA + stats)
│   ├── retornos.py    build_retornos_sections (cumulative return + drawdown)
│   └── volatilidade.py build_volatilidade_sections (rolling vol + BB)
└── modes/             one file per mode, auto-discovered via importlib
    ├── __init__.py    minimal package marker
    ├── dashboard.py   @register_mode("dashboard") — 5-tab deep dive (default)
    └── quote.py       @register_mode("quote")     — latest OHLCV snapshot
```

### Test module tree

```text
tests/skills/b3/price/
├── conftest.py        price_env fixture — synthetic cotahist.db (10 PETR4 days)
├── test_dashboard.py  TestDashboardMode (2 tests — error path + 5-tab structure)
└── test_route.py      TestPriceRoute (2 tests — no-mode error + manifest modes)
```

4 tests total (v1.0).

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
  │  3. compute_52w_range + latest_quote (for KPIs)
  │  4. Pass computed arrays to report/ builders (no recomputation in builders)
  │  5. Build 5 tabs: Cotação, Médias Móveis, Volume, Retornos, Volatilidade
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

### Report builder inventory

| Function | Returns | Section types emitted |
|----------|---------|------------------------|
| `build_quote_kpis(quote, prev_close, range_52w)` | `[{type:kpi, label, value, unit, subtitle, delta}]` | 6 KPI cards |
| `build_cotacao_sections(ticker, ohlcv, ma20, ma50, ma100, ma200)` | `[candlestick, chart]` | Candlestick + volume bars |
| `build_medias_sections(ticker, dates, closes, ma20, ma50, ma100, ma200, crossovers)` | `[chart, table]` | SMA line + crossover table |
| `build_volume_sections(ticker, dates, volumes, closes, opens, vol_ma20=None)` | `[chart, table]` | Volume bars + stats |
| `build_retornos_sections(ticker, dates, closes, cum_returns, drawdowns)` | `[chart, chart, table]` | Cumulative + drawdown + KPIs |
| `build_volatilidade_sections(ticker, dates, closes, vol_20d, vol_60d, vol_252d, bb_*)` | `[chart, chart, table]` | Rolling vol + BB + KPIs |

## Candlestick Chart Shape

The candlestick chart_data is consumed by `chartjs-chart-financial` v0.2.0.
The dashboard template adds this CDN script in `{% block scripts %}`:

```html
<script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.0/dist/chartjs-chart-financial.min.js"></script>
```

Each candle is an object `{"t": "YYYY-MM-DD", "o": float, "h": float, "l": float, "c": float}`.
The chart_data also includes 4 line datasets (MA20/50/100/200) as overlays.
The dual-axis (price left, volume right) is configured via `scales.y` + `scales.y1`.

The `sec.type == "candlestick"` branch in `dashboard.html` + `macros.html`
renders the canvas and wires up `_renderChart()` with the financial plugin.

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
| `dashboard` | 10Y window | COTAHIST | 5-tab dashboard payload (Cotação / Médias / Volume / Retornos / Volatilidade) + 6 KPIs |
| `quote` | — | COTAHIST | Latest OHLCV + 52-week range + 6 KPI cards |

## Sync Guard (v1.0)

`REQUIRED_SOURCES = ["cotahist"]` wired via `make_route()`.

- `route()` calls `ensure_fresh()` before each dispatch — checks `cotahist.sync_state.last_synced_at`.
- If stale (> 24h) or missing, triggers `sync(year=current_year, force=True)`.
- Re-entrancy guard: nested `route()` calls (none currently, but reserved for future composable modes) trigger `ensure_fresh()` at most once.
- Escape hatches: `CVM_SKIP_SYNC=1` env var (set in conftest for tests) + `route(..., skip_sync=True)` kwarg.

---

*Last updated: 2026-08-06 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
