<- Back to [Backtest Overview](../BACKTEST.md)

# 🗺️ Changelog

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-07-29 | **File structure split + dashboard mode.** `backtest.py` (530 lines) split into standard modular structure: `_registry.py` + `modes/` (4 files: run, strategies, results, dashboard) + `helpers.py` + `report.py`. NEW `dashboard` mode — 3-tab dashboard (Overview with KPIs + equity curve, Trades table, Performance summary). Auto-discovery via importlib. |
| **v1.0** | 2026-07-26 | **Initial implementation.** 3 modes: run, strategies, results. 6 built-in strategies using calculations metrics (value_pe, value_pvpa, quality_roe, quality_roic, income_dy, composite). Performance metrics: CAGR, total return, max drawdown, Sharpe ratio, win rate, alpha vs buy & hold. Equity curve + trade log. 19 tests. |

---

*Last updated: 2026-07-29 (v1.1).*
