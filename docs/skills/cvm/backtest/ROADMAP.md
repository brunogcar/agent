<- Back to [Backtest Overview](../BACKTEST.md)

# 🗺️ Backtest ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | B1 — Monthly returns heatmap | Monthly returns table + color-coded heatmap |
| P2 | B2 — Trade distribution histogram | PnL distribution per trade |
| P3 | B3 — Multi-position support | Currently max_positions=1 only |
| P3 | B4 — More strategies | Mean reversion, momentum, sector rotation |
| Done | v1.2 dashboard reorg | Added drawdown chart to Performance tab |
| Done | Sync guard (v1.2) | required_sources wired via make_route() |
| Done | F7 engine cache (v1.9) | Inherited from calculations skill |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### B1 — Monthly returns heatmap

**Priority:** P2

Add a monthly returns table showing % return per month, color-coded
(green for positive, red for negative). Would group trades by exit month
and compute the return for each month.

### B2 — Trade distribution histogram

**Priority:** P2

A histogram showing the distribution of trade returns (PnL %). Helps
visualize whether the strategy has fat tails, skew, or is normally
distributed.

### B3 — Multi-position support

**Priority:** P3

Currently `max_positions=1` is the only supported value. Adding
multi-position support would allow portfolio backtesting with
diversification across tickers.

### B4 — More strategies

**Priority:** P3

Add built-in strategies beyond `value_pe`: mean reversion, momentum,
sector rotation, dividend-focused.

---

*Last updated: 2026-08-01. See [CHANGELOG.md](CHANGELOG.md) for version history.*
