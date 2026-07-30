<- Back to [INSIDER Overview](../INSIDER.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-25 | **Modular split + dashboard mode.** Split the 91-line `insider.py` into `_registry.py` + `modes/{history,by_role,summary,dashboard}.py` + `report.py` (NEW dashboard composition helpers) + auto-discovery in `__init__.py`. Added a new `dashboard` mode (4 tabs: Overview / Recent Transactions / By Role / Monthly Net; 4 top-level KPI cards: Sentimento / Volume Comprado / Volume Vendido / Net Volume). Added a new `insider_dashboard` report adapter under `tools/report_ops/adapters/` (74-adapter count). Mirrors the governance v1.1 / shareholders v1.1 / screener v1.4 split pattern. `insider.py` deleted. 26 tests pass (11 original incl. 1 NEW route dispatch test + 15 NEW TestDashboardMode) + 11 NEW TestInsiderDashboardAdapter tests. |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: history, by_role, summary. Wraps VLMO query_engine with bridge resolution + data freshness. Summary computes sentiment (buying/selling/neutral) + net_volume. 12 tests. 3 report adapters. |

---

*Last updated: 2026-07-25 (v1.1).*
