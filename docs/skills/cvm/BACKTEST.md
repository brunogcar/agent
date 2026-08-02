<- Back to [CVM Skills](../CVM.md)

# 📊 BACKTEST — Strategy Backtesting Skill

Backtesting engine for CVM strategies. Uses calculations engines + metrics for signal generation + return computation. Reuses the same 18 engines + 21 metrics as the historical skill — no data duplication.

**Key characteristics:**
- **6 built-in strategies** — value_pe, value_pvpa, quality_roe, quality_roic, income_dy, composite
- **Calculations integration** — signals use `pe_at()`, `roe_at()`, `roic_at()`, `dy_at()`, `pvpa_at()` from calculations metrics
- **Performance metrics** — CAGR, total return, max drawdown, Sharpe ratio, win rate, alpha vs buy & hold
- **Equity curve** — daily equity tracking for charting
- **Trade log** — entry/exit dates, prices, PnL, return %, holding days, exit reason
- **Buy & hold comparison** — alpha = strategy return - buy & hold return
- **4 modes** — run (execute strategy), strategies (list available), results (analyze), dashboard (3-tab composition: Overview/Trades/Performance)

---

## 🚀 Quick Start

```
# List available strategies
skill(domain="cvm", sub_domain="backtest", mode="strategies")

# Run value_pe strategy on PETR4 (3-year backtest, BRL 10k initial)
skill(domain="cvm", sub_domain="backtest", mode="run", params='{"ticker":"PETR4","strategy":"value_pe"}')

# Run composite strategy on VALE3 with custom dates
skill(domain="cvm", sub_domain="backtest", mode="run", params='{"ticker":"VALE3","strategy":"composite","start_date":"2022-01-01","end_date":"2024-12-31"}')
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](backtest/ARCHITECTURE.md) | Strategy design, backtest loop, performance metrics, calculations integration |
| [API.md](backtest/API.md) | 4 modes: run, strategies, results, dashboard |
| [CHANGELOG.md](backtest/CHANGELOG.md) | Version history |
| [ROADMAP.md](backtest/ROADMAP.md) | Backlog + priorities (benchmark comparison, monthly heatmap, Sortino) |
| [INSTRUCTIONS.md](backtest/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg + sync guard; see CHANGELOG.md).*
