<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-07-28 | **Test rename + count fix.** Renamed `test_tier4_metrics.py` → `test_fundamental_ratios.py` and `test_tier56_metrics.py` → `test_capex_current_ratio.py` (descriptive names — no version numbers in filenames). Fixed stale count assertions: `test_total_engines_is_16`/`test_total_metrics_is_17` → `test_engine_count`/`test_metric_count` with `>= 18`/`>= 21` floor assertions (no hardcoded numbers in test names; future additions won't break them). Updated 7 architecture docs (16→18 engines, 17→21 metrics, 6→7 categories, 5→8 per-share+ratio, 12→13 fundamental). EBIT engine gained description-search fallback for non-standard DRE filers (banks/insurers). da/capex engines scoped to correct DFC sections (6.01/6.02) + accent-normalized exclusion of financing/disposal lines. |
| **v1.0** | 2026-07-26 | **Extracted from historical v2.1.** 16 engines + 17 metrics + central `_registry.py` moved from `skills/cvm/historical/` to `skills/cvm/calculations/`. All import paths updated. Historical skill now imports from calculations. This is the shared foundation for all CVM skills — valuation, financials, and future backtest will import from here. 355 tests pass. |

---

*Last updated: 2026-07-28 (v1.1).*
