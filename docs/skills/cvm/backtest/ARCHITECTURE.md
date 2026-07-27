<- Back to [Backtest Overview](../BACKTEST.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/backtest/__init__.py` | MANIFEST + route — 3 modes |
| `skills/cvm/backtest/backtest.py` | Main: run(), strategies(), results() + 6 built-in strategies |
| `skills/cvm/_freshness.py` | add_freshness() — shared by all CVM skills |
| `skills/cvm/calculations/engines/price.py` | price_series() — daily close prices for backtest |
| `skills/cvm/calculations/metrics/*.py` | 21 metric *_at() functions for signal generation |

## 🌳 Module Tree

```
skills/cvm/backtest/
├── __init__.py           # MANIFEST + route
└── backtest.py           # run(), strategies(), results() + BUILTIN_STRATEGIES
```

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
├── conftest.py       # env vars
├── test_route.py     # 7 tests (validation + route dispatch)
├── test_run.py       # 8 tests (strategies list + run mode with mocked prices)
└── test_results.py   # 4 tests (results analysis)
```

---

*Last updated: 2026-07-26 (v1.0).*
