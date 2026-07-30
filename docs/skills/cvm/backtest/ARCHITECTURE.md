<- Back to [Backtest Overview](../BACKTEST.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/backtest/__init__.py` | MANIFEST + route — 4 modes (auto-discovery via importlib on `modes/*.py`) |
| `skills/cvm/backtest/_registry.py` | `MODES` dict + `@register_mode` decorator + `build_manifest_modes()` |
| `skills/cvm/backtest/modes/run.py` | `run()` — execute a strategy on a ticker over a date range |
| `skills/cvm/backtest/modes/strategies.py` | `strategies()` — list available built-in strategies |
| `skills/cvm/backtest/modes/results.py` | `results()` — analyze backtest results (CAGR, Sharpe, drawdown) |
| `skills/cvm/backtest/modes/dashboard.py` | `dashboard()` — 3-tab dashboard (Overview/Trades/Performance) |
| `skills/cvm/backtest/helpers.py` | `BUILTIN_STRATEGIES` + signal helpers (`_precompute_signals`, `_lookup_signal`) |
| `skills/cvm/backtest/report.py` | Report wiring helpers for the backtest skill |
| `skills/cvm/_freshness.py` | add_freshness() — shared by all CVM skills |
| `skills/cvm/calculations/engines/price.py` | price_series() — daily close prices for backtest |
| `skills/cvm/calculations/metrics/*.py` | 21 metric *_at() functions for signal generation |

## 🌳 Module Tree

```
skills/cvm/backtest/
├── __init__.py           # MANIFEST + route (auto-discovery)
├── _registry.py          # MODES dict + @register_mode + build_manifest_modes()
├── helpers.py            # BUILTIN_STRATEGIES + signal helpers
├── report.py             # report wiring helpers
└── modes/
    ├── __init__.py
    ├── run.py            # run() — execute strategy
    ├── strategies.py     # strategies() — list built-in strategies
    ├── results.py        # results() — analyze results
    └── dashboard.py      # dashboard() — 3-tab composition
```

[v1.1] Migrated from a single-file `backtest.py` (530 lines) to the standard
modular `modes/ + _registry.py` pattern (mirroring `financials` v1.6 +
`valuation` v1.4 + `calculations`). Adding a new mode = drop a file in `modes/`
+ `@register_mode(...)`; no edits to `__init__.py`.

## 🔄 Backtest Loop

```
run(ticker, strategy, start_date, end_date)
  │
  ├── price_series(ticker, start_date, end_date)  → COTAHIST daily prices
  │
  └── For each daily bar:
        ├── If in position: check exit (max_holding or exit_fn)
        │   └── Exit: record trade, update capital
        ├── If not in position: check signal_fn(ticker, date)
        │   └── Entry: buy with all capital, record position
        ├── Track equity (cash + position value)
        ├── Track max drawdown
        └── Track daily returns (for Sharpe)
  │
  ├── Close open position at end
  ├── Compute CAGR, Sharpe, win rate, alpha
  └── Return {performance, trades, equity_curve}
```

## 📐 Strategy Design

Each strategy is a dict with:
- `name`: str
- `description`: str
- `signal`: fn(ticker, date) -> bool — uses calculations metrics
- `exit`: fn(ticker, date, entry_date) -> bool — optional (default: hold to max_holding)
- `max_holding_days`: int (default: 252 = 1 year)

### Built-in strategies:

| Strategy | Signal | Metric used |
|----------|--------|-------------|
| value_pe | P/L < 5 | `pe_at()` from lpa metric |
| value_pvpa | P/VPA < 1.0 | `pvpa_at()` from vpa metric |
| quality_roe | ROE > 20% | `roe_at()` from roe metric |
| quality_roic | ROIC > 15% | `roic_at()` from roic metric |
| income_dy | Div Yield > 6% | `dy_at()` from dpa metric |
| composite | P/L < 8 AND ROE > 15% | `pe_at()` + `roe_at()` |

## 📊 Performance Metrics

| Metric | Formula |
|--------|---------|
| total_return_pct | (final_equity / initial_capital - 1) × 100 |
| cagr_pct | ((final / initial) ^ (1/years) - 1) × 100 |
| max_drawdown_pct | max((peak - trough) / peak) × 100 |
| sharpe_ratio | (avg_daily_return / std_daily_return) × √252 |
| win_rate_pct | (winning_trades / total_trades) × 100 |
| buy_hold_return_pct | (last_price / first_price - 1) × 100 |
| alpha_vs_buy_hold | total_return - buy_hold_return |

## 🧪 Testing

```
tests/skills/cvm/backtest/
├── conftest.py         # env vars
├── test_route.py       # 11 tests (validation + route dispatch + manifest modes)
├── test_run.py         # 14 tests (strategies list + run mode with mocked prices)
├── test_results.py     # 4 tests (results analysis)
└── test_dashboard.py   # 9 tests (dashboard mode — 3-tab composition)  (v1.1)
```

---

*Last updated: 2026-07-29 (v1.1).*
