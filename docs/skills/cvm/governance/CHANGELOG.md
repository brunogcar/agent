<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.2** | 2026-07-31 | **Dashboard reorg + sync guard.** Added 1 chart builder to `report.py`: `build_practices_doughnut` (doughnut chart showing distribution of practice compliance levels Adequado / Parcialmente / Não Adequado, on Practices tab). Wired sync guard via `required_sources=["cgvn","bridge"]` + `make_route()`. Added detailed `print("[governance] ...")` progress output (flush=True) showing starting message, data fetching (score/practices/by-chapter), building sections, done message with tab count. Created `ROADMAP.md` with 4 backlog items (per-chapter doughnuts, multi-year trend, peer comparison, practice drill-down). 6 tests (was 5). |
| **v2.0** | 2026-07-30 | **skills/_base/ extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base/` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base/) instead of 11. |
| v1.1 | 2026-07-29 | **Modular split + dashboard mode.** Split monolithic `governance.py` (75 lines) into `_registry.py` + `modes/` (4 mode files: practices, score, by_chapter, dashboard) + `report.py` — mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends` modular pattern (`_registry.py` + `modes/*.py` auto-discovered via `@register_mode`). New `dashboard` mode produces a multi-tab dashboard payload for the report tool. New `governance_dashboard` adapter (report tool v1.7, 70th adapter). 4 modes total (was 3). |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: practices, score, by_chapter. Wraps CGVN query_engine with bridge resolution + data freshness. Score computes % Sim/Não/Parcialmente. 12 tests. 3 report adapters. |

---

*Last updated: 2026-07-31 (v1.2).*
