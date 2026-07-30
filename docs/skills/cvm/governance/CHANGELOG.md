<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-29 | **Modular split + dashboard mode.** Split monolithic `governance.py` (75 lines) into `_registry.py` + `modes/` (4 mode files: practices, score, by_chapter, dashboard) + `report.py` — mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends` modular pattern (`_registry.py` + `modes/*.py` auto-discovered via `@register_mode`). New `dashboard` mode produces a multi-tab dashboard payload for the report tool. New `governance_dashboard` adapter (report tool v1.7, 70th adapter). 4 modes total (was 3). |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: practices, score, by_chapter. Wraps CGVN query_engine with bridge resolution + data freshness. Score computes % Sim/Não/Parcialmente. 12 tests. 3 report adapters. |

---

*Last updated: 2026-07-29 (v1.1).*
