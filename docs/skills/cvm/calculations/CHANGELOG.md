<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.3** | 2026-07-28 | **P2 sprint: 10 new engines + 15 new metrics.** New BPA engines: receivables (1.01.03), inventory (1.01.04), ppe (1.02.03), intangibles (1.02.04). New BPP engine: payables (2.01.01). New DRE engines: cogs (3.02), financial_result (3.06). New DVA category + 3 engines: dva_interest_paid (8.3), dva_total_tax (8.2), dva_value_added (7). New metrics (engines existed): ev_sales, ev_fcf, cash_ratio, ocf_margin, fcf_margin, working_capital, cash_flow_to_debt, retention_ratio, sustainable_growth. New metrics (new engines): quick_ratio, interest_coverage, inventory_turnover, receivables_turnover, fixed_asset_turnover, price_to_tangible_book. Now 30 engines + 37 metrics. |
| **v1.2** | 2026-07-28 | **Hardening: 5-review synthesis.** P0 correctness fixes: ROA + Asset Turnover repointed from `assets_at` (codigo 1.01, current assets) to `total_assets_at` (codigo 1, total assets) — was silently overstating both ratios ~2-5x; `assets.py` renamed → `current_assets.py` with correct function names. P1 new engines: EBT (3.07, with description-search fallback for banks/insurers) + Financing CF (6.03, FCF). P1 description-search fallback added to revenue/tax/earnings engines (ebit already had it). P1 ROIC formula corrected: `NOPAT = EBIT × (1 - tax/EBT)` (was `EBIT - tax_expense` approximation). P1 new metric: `effective_tax_rate` (tax/EBT, PT aliases: taxa_efetiva, aliquota_efetiva). P1 financials/metrics.py migrated to use calculations engines (2 new engine-backed functions). Test cleanup: deleted 5 duplicate/stale files, fixed test_p_fco.py copy-paste bug (was testing p_ebit), filled test_p_ebit.py + test_p_fcf.py empty stubs. Now 20 engines + 22 metrics. ROADMAP.md added documenting P2/P3 deferred items. |
| **v1.1** | 2026-07-28 | **Test rename + count fix.** Renamed `test_tier4_metrics.py` → `test_fundamental_ratios.py` and `test_tier56_metrics.py` → `test_capex_current_ratio.py` (descriptive names — no version numbers in filenames). Fixed stale count assertions: `test_total_engines_is_16`/`test_total_metrics_is_17` → `test_engine_count`/`test_metric_count` with `>= 18`/`>= 21` floor assertions (no hardcoded numbers in test names; future additions won't break them). Updated 7 architecture docs (16→18 engines, 17→21 metrics, 6→7 categories, 5→8 per-share+ratio, 12→13 fundamental). EBIT engine gained description-search fallback for non-standard DRE filers (banks/insurers). da/capex engines scoped to correct DFC sections (6.01/6.02) + accent-normalized exclusion of financing/disposal lines. |
| **v1.0** | 2026-07-26 | **Extracted from historical v2.1.** 16 engines + 17 metrics + central `_registry.py` moved from `skills/cvm/historical/` to `skills/cvm/calculations/`. All import paths updated. Historical skill now imports from calculations. This is the shared foundation for all CVM skills — valuation, financials, and future backtest will import from here. 355 tests pass. |

---

*Last updated: 2026-07-28 (v1.3).*
