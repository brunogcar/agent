<- Back to [Backtest Overview](../BACKTEST.md)

# 🗺️ Changelog

| Version | Date | Summary |
|---------|------|---------|
| **v2.0** | 2026-07-30 | **skills/_base.py extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base.py` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base.py) instead of 11. |
| **v1.1** | 2026-07-29 | **File structure split + dashboard mode.** `backtest.py` (530 lines) split into standard modular structure: `_registry.py` + `modes/` (4 files: run, strategies, results, dashboard) + `helpers.py` + `report.py`. NEW `dashboard` mode — 3-tab dashboard (Overview with KPIs + equity curve, Trades table, Performance summary). Auto-discovery via importlib. |
| **v1.0** | 2026-07-26 | **Initial implementation.** 3 modes: run, strategies, results. 6 built-in strategies using calculations metrics (value_pe, value_pvpa, quality_roe, quality_roic, income_dy, composite). Performance metrics: CAGR, total return, max drawdown, Sharpe ratio, win rate, alpha vs buy & hold. Equity curve + trade log. 19 tests. |

---

*Last updated: 2026-07-30 (v2.0).*
