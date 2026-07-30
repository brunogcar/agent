<- Back to [Backtest Overview](../BACKTEST.md)

# 📝 API Reference

## 🔧 Modes

### `mode="run"` (default)
Run a backtest strategy on a single ticker.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | B3 ticker (e.g., PETR4) |
| `strategy` | `str` | `value_pe` | Strategy name |
| `start_date` | `str` | 3 years ago | Backtest start (YYYY-MM-DD) |
| `end_date` | `str` | today | Backtest end (YYYY-MM-DD) |
| `initial_capital` | `float` | `10000` | Starting capital in BRL |
| `max_positions` | `int` | `1` | Max simultaneous positions |

Returns:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "strategy": "value_pe",
  "start_date": "2021-07-26",
  "end_date": "2024-07-26",
  "initial_capital": 10000,
  "final_equity": 12500.0,
  "performance": {
    "total_return_pct": 25.0,
    "cagr_pct": 7.72,
    "max_drawdown_pct": 12.5,
    "sharpe_ratio": 1.15,
    "win_rate_pct": 66.7,
    "num_trades": 3,
    "buy_hold_return_pct": 15.0,
    "alpha_vs_buy_hold": 10.0
  },
  "trades": [...],
  "equity_curve": [...]
}
```

### `mode="strategies"`
List all available built-in strategies.

Returns:
```json
{
  "status": "ok",
  "strategies": [
    {"name": "value_pe", "description": "Buy when P/L < 5", "max_holding_days": 252},
    ...
  ],
  "count": 6
}
```

### `mode="results"`
Analyze backtest results — extract key metrics.

| Param | Type | Default | Description |
|---|---|---|---|
| `backtest_result` | `dict` | (required) | The dict returned by `run()` |

Returns:
```json
{
  "status": "ok",
  "summary": {
    "total_return_pct": 25.0,
    "cagr_pct": 7.72,
    "max_drawdown_pct": 12.5,
    "sharpe_ratio": 1.15,
    "win_rate_pct": 66.7,
    "alpha_vs_buy_hold": 10.0
  },
  "trade_analysis": {
    "num_trades": 3,
    "avg_holding_days": 84.0,
    "avg_return_per_trade_pct": 8.33,
    "best_trade": {"entry_date": "...", "exit_date": "...", "return_pct": 15.0},
    "worst_trade": {"entry_date": "...", "exit_date": "...", "return_pct": -5.0}
  }
}
```

### `mode="dashboard"`  (v1.1)
Multi-tab dashboard composition for a single ticker — 3 tabs (Overview / Trades / Performance). Runs the backtest internally + assembles typed sections ready for the `backtest_dashboard` report adapter.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | B3 ticker (e.g., PETR4) |
| `strategy` | `str` | `value_pe` | Strategy name |
| `start_date` | `str` | 3 years ago | Backtest start (YYYY-MM-DD) |
| `end_date` | `str` | today | Backtest end (YYYY-MM-DD) |
| `initial_capital` | `float` | `10000` | Starting capital in BRL |

Returns a dict with a `tabs` list (each tab has `name` + typed `sections`). Pipe into the report tool with `config={"adapter":"backtest_dashboard"}`.

## 🛠️ Tool Invocation

```python
skill(domain="cvm", sub_domain="backtest", mode="run",
      params='{"ticker":"PETR4","strategy":"value_pe"}')
```

## 📊 Report Adapters

The backtest equity_curve can be rendered as a line chart:
```python
report(action="chart", title="PETR4 Backtest Equity Curve",
       data={"x": [e["date"] for e in equity_curve],
             "datasets": [{"label": "Equity", "data": [e["equity"] for e in equity_curve]}]},
       config={"chart_type": "line"})
```

---

*Last updated: 2026-07-29 (v1.1).*
