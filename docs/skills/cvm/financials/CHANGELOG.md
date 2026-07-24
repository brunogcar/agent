<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **Collective LLM review fixes (3 bugs + 6 suggestions).** (P0) Cross-database empresa_ids — DFP and ITR have independent autoincrement IDs; now resolves separately per DB. (P1) Q1 derivation subtracted prior-year DFP — fixed: Q1 standalone = Q1 cumulative. (P1) summary latest_quarterly returned oldest quarter — fixed: periods[-1]. (S) Negative PL guard — ROE/debt ratios return None when PL ≤ 0. (S) Payout = None in quarterly mode (DVA is annual-only). (S) EBITDA method provenance field (ebit+da/ebit_only/none). (S) SUMMARY_CODES now imports from catalog RESUMO_ACCOUNTS (dedup). (S) Deleted dead derive_standalone_quarters(). 4 new regression tests. |
| v1.0 | 2026-07-23 | **Initial implementation.** 4 modes: quarterly (default, 8Q), annual (5Y), complete (by grupo + key codes), summary. Standalone quarter derivation from ITR cumulative + DFP annual. EBITDA = EBIT + D&A (DFC 6.01.01.02). Ratios: margins, ROA/ROE (annualized for quarterly), debt ratios, payout. 23 tests. Read-only — calls DFP/ITR query engines directly. |

---

## 🔄 In Progress / Next Up

- **TTM-based ratios** — Currently ROA/ROE are annualized (×4) for quarterly. Rapina uses TTM (trailing twelve months) for some ratios. Implement TTM EBITDA for `Dív.Líq./EBITDA TTM` ratio. `compute_ttm_ebitda()` stub already exists.
- **Average balance sheet for ROA/ROE** — Rapinav2 averages balance-sheet values for TTM/annual ratio denominators. Currently uses period-end (overstates volatility).
- **xlsx export** — Export to .xlsx format (like rapina's JHSF example) with multiple sheets (completo anual/trim, resumo anual/trim). Likely a `report` tool action or a skill feature.
- **Charts/graphs** — Visual charts for trends (revenue, margins, debt evolution). Belongs in `report` tool.
- **Individual (non-consolidated)** — Already supported via `consolidado=0` but needs testing with real data.
- **IPCA inflation adjustment** — Normalize historical BRL to present value for multi-year comparisons.
- **Sector benchmarks** — Compute sector medians (P/L, EV/EBITDA, ROE by sector) by aggregating financials across companies.
- **QoQ growth** — Quarter-over-quarter % change for revenue, EBITDA, net income. Trivial from standalone series.
- **Data freshness indicator** — Expose `last_sync_at` in responses so consumers know data age.
- **DFC_MD filer support** — EBITDA for direct-method filers (D&A in different sub-accounts). Currently falls back to EBIT with `ebitda_method="ebit_only"` provenance.
- **Restatement awareness** — `restated: true` flag when VERSAO > 1.

---

## 🚫 Deferred / Out of Scope

- **All 497 account codes** — `complete` mode returns key codes only (~30 codes across 5 grupos). Full hierarchy export deferred (too noisy for LLM context).
- **Historical restatements** — Currently keeps only the latest version (VERSAO dedup). Showing restated vs original is deferred.
- **Cross-company comparison** — Comparing multiple companies side-by-side is a separate skill (e.g., `skills/cvm/comparison`).

---

*Last updated: 2026-07-23 (v1.0).*
