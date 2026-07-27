<- Back to [Backtest Overview](../BACKTEST.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never query CVM/B3 directly — use calculations engines/metrics for signals.
2. Never modify BUILTIN_STRATEGIES at runtime in production code.
3. Never create `.bak` files.
4. Never print to stdout — MCP stdio corruption.

## ✅ ALWAYS DO

1. Always use calculations metric `*_at()` functions for signal generation.
2. Always wrap signal calls in try/except — missing data is non-fatal.
3. Always track equity curve for every bar.
4. Always compute buy & hold comparison for alpha.
5. Always close open positions at end of backtest period.

---

*Last updated: 2026-07-26 (v1.0).*
