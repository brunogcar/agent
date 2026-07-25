<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1+report | 2026-07-25 | **Report wiring (no skill change).** The `financials` result can now be rendered as a table or exported to xlsx via the report tool's adapters: `financials_quarterly`, `financials_annual`, `financials_summary` (`config["adapter"]`). Number formatting (BRL/%) is handled by `report_ops/formats.py`. See [CVM Skills — Report Integration](../../CVM.md#-report-integration-v12). |
| v1.0.1 | 2026-07-23 | **Collective LLM review fixes (3 bugs + 6 suggestions).** (P0) Cross-database empresa_ids — DFP and ITR have independent autoincrement IDs; now resolves separately per DB. (P1) Q1 derivation subtracted prior-year DFP — fixed: Q1 standalone = Q1 cumulative. (P1) summary latest_quarterly returned oldest quarter — fixed: periods[-1]. (S) Negative PL guard — ROE/debt ratios return None when PL ≤ 0. (S) Payout = None in quarterly mode (DVA is annual-only). (S) EBITDA method provenance field (ebit+da/ebit_only/none). (S) SUMMARY_CODES now imports from catalog RESUMO_ACCOUNTS (dedup). (S) Deleted dead derive_standalone_quarters(). 4 new regression tests. |
| v1.0 | 2026-07-23 | **Initial implementation.** 4 modes: quarterly (default, 8Q), annual (5Y), complete (by grupo + key codes), summary. Standalone quarter derivation from ITR cumulative + DFP annual. EBITDA = EBIT + D&A (DFC 6.01.01.02). Ratios: margins, ROA/ROE (annualized for quarterly), debt ratios, payout. 23 tests. Read-only — calls DFP/ITR query engines directly. |

---

## ✅ Now Available (via report tool, v1.2)

- **xlsx export** — `report(action="export", data=<financials JSON>, config={"format":"xlsx","adapter":"financials_annual"})`. Each section becomes a sheet; numeric cells stay native with Excel number formats. (Was a roadmap item; delivered by `tools/report_ops/export.py` + `adapters/financials.py`.)
- **Tabular rendering** — `report(action="table", data=<financials JSON>, config={"adapter":"financials_quarterly"})`. Wide period × metric table with per-column BRL/% formatting + search. (Was "belongs in report tool"; now done.)
- **Charts** — *Partially.* Trend charts (revenue/EBITDA over time) are on the report tool roadmap as a `financials_quarterly_chart` adapter (v1.3). For now, render the table and the LLM can call `report(action="chart", ...)` with extracted series.

---

## 🔄 In Progress / Next Up

- **TTM-based ratios** — Currently ROA/ROE are annualized (×4) for quarterly. Rapina uses TTM (trailing twelve months) for some ratios. Implement TTM EBITDA for `Dív.Líq./EBITDA TTM` ratio. `compute_ttm_ebitda()` stub already exists.
- **Average balance sheet for ROA/ROE** — Rapinav2 averages balance-sheet values for TTM/annual ratio denominators. Currently uses period-end (overstates volatility).
- **Trend chart adapter** — `financials_quarterly_chart` adapter (revenue/EBITDA/margins over time) → `report(action="chart")`. Tracked in [report CHANGELOG roadmap](../../../tools/report/CHANGELOG.md).
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

*Last updated: 2026-07-25 (v1.0.1 + report wiring).*
