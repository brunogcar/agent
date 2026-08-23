<- Back to [INSIDER Overview](../INSIDER.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.2** | 2026-08-02 | **Dashboard reorg (charts + print output).** Added 2 Chart.js chart builders to `report.py`: `build_monthly_net_chart(summary_result)` (bar chart of monthly net insider volume — teal for net-buy months, red for net-sell months) + `build_cumulative_chart(transactions)` (line chart of cumulative signed volume over time, using history()'s movements). Both return `{"type": "chart", "chart_data": <Chart.js config>}` or None when there's no data. Dashboard mode now appends the cumulative chart to the Recent Transactions tab + the monthly net chart to the Monthly Net tab (both skipped gracefully when their builder returns None). Added detailed `[insider]` print output (flush=True) showing the starting message, per-data-fetch progress (summary / history / by_role), section-building step, + final "Done! N tabs, M KPIs" line. ROADMAP.md created. No sync guard (VLMO sync function signature differs — left `make_route("sub_domain", "insider", MODES)` as-is). 7 dashboard tests (was 6 — added 1 chart assertion test). |
| **v2.0** | 2026-07-30 | **skills/_base/ extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base/` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base/) instead of 11. |
| v1.1 | 2026-07-25 | **Modular split + dashboard mode.** Split the 91-line `insider.py` into `_registry.py` + `modes/{history,by_role,summary,dashboard}.py` + `report.py` (NEW dashboard composition helpers) + auto-discovery in `__init__.py`. Added a new `dashboard` mode (4 tabs: Overview / Recent Transactions / By Role / Monthly Net; 4 top-level KPI cards: Sentimento / Volume Comprado / Volume Vendido / Net Volume). Added a new `insider_dashboard` report adapter under `tools/report_ops/adapters/` (74-adapter count). Mirrors the governance v1.1 / shareholders v1.1 / screener v1.4 split pattern. `insider.py` deleted. 26 tests pass (11 original incl. 1 NEW route dispatch test + 15 NEW TestDashboardMode) + 11 NEW TestInsiderDashboardAdapter tests. |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: history, by_role, summary. Wraps VLMO query_engine with bridge resolution + data freshness. Summary computes sentiment (buying/selling/neutral) + net_volume. 12 tests. 3 report adapters. |

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg).*
