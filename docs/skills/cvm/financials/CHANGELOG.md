<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2 | 2026-07-25 | **DFC_MD filer support.** Added D| v1.1 | 2026-07-25A fallback codes for direct-method DFC filers (DFC_MD). _extract_metrics now tries 6.01.01.02 (DFC_MI indirect) first, then 6.02.01.02 + 6.01.04 (DFC_MD direct). EBITDA for direct-method filers now uses real D| v1.1 | 2026-07-25A instead of falling back to ebit_only. 5 new tests.
| v1.1 | 2026-07-25 | **TTM ratios.** Quarterly mode now returns a `ttm` field: trailing twelve months summary computed from the last 4 standalone quarters. Flows (revenue, EBIT, EBITDA, lucro_liquido, FCO) are summed; snapshots (ativo_total, caixa, PL, divida_bruta) are averaged. TTM ROA/ROE replace the v1.0.1 annualized (×4) approach — more accurate for seasonal businesses. New `compute_ttm(periods)` function in metrics.py. |
| v1.0.1+report | 2026-07-25 | **Report wiring (no skill change).** The `financials` result can now be rendered as a table or exported to xlsx via the report tool's adapters: `financials_quarterly`, `financials_annual`, `financials_summary` (`config["adapter"]`). Number formatting (BRL/%) is handled by `report_ops/formats.py`. See [CVM Skills — Report Integration](../../CVM.md#-report-integration-v12). |
| v1.0.1 | 2026-07-23 | **Collective LLM review fixes (3 bugs + 6 suggestions).** (P0) Cross-database empresa_ids — DFP and ITR have independent autoincrement IDs; now resolves separately per DB. (P1) Q1 derivation subtracted prior-year DFP — fixed: Q1 standalone = Q1 cumulative. (P1) summary latest_quarterly returned oldest quarter — fixed: periods[-1]. (S) Negative PL guard — ROE/debt ratios return None when PL ≤ 0. (S) Payout = None in quarterly mode (DVA is annual-only). (S) EBITDA method provenance field (ebit+da/ebit_only/none). (S) SUMMARY_CODES now imports from catalog RESUMO_ACCOUNTS (dedup). (S) Deleted dead derive_standalone_quarters(). 4 new regression tests. |
| v1.0 | 2026-07-23 | **Initial implementation.** 4 modes: quarterly (default, 8Q), annual (5Y), complete (by grupo + key codes), summary. Standalone quarter derivation from ITR cumulative + DFP annual. EBITDA = EBIT + D&A (DFC 6.01.01.02). Ratios: margins, ROA/ROE (annualized for quarterly), debt ratios, payout. 23 tests. Read-only — calls DFP/ITR query engines directly. |

---

## ✅ Now Available (via report tool, v1.2 + v1.2.2)

- **xlsx export** — `report(action="export", data=<financials JSON>, config={"format":"xlsx","adapter":"financials_annual"})`. Each section becomes a sheet; numeric cells stay native with Excel number formats.
- **Tabular rendering** — `report(action="table", data=<financials JSON>, config={"adapter":"financials_quarterly"})`. Wide period × metric table with per-column BRL/% formatting + search.
- **Trend charts** — `report(action="chart", data=<financials JSON>, config={"chart_type":"line","adapter":"financials_quarterly_chart"})`. Multi-series line chart (Receita + EBITDA + Lucro Líquido over time). Delivered in report v1.2.2.
- **TTM ratios** — ✅ v1.1 (was roadmap item). Quarterly mode now returns `ttm` summary.

---

## 🔄 In Progress / Next Up

- **Average balance sheet for ROA/ROE** — Rapinav2 averages balance-sheet values for TTM/annual ratio denominators. TTM now uses average of 4 (v1.1), but annual still uses period-end.
- **Individual (non-consolidated)** — Already supported via `consolidado=0` but needs testing with real data.
- **IPCA inflation adjustment** — Normalize historical BRL to present value for multi-year comparisons.
- **Sector benchmarks** — Compute sector medians (P/L, EV/EBITDA, ROE by sector) by aggregating financials across companies.
- **QoQ growth** — Quarter-over-quarter % change. Now available via `comparison` skill `growth` mode.
- **Data freshness indicator** — Expose `last_sync_at` in responses so consumers know data age.
- **DFC_MD filer support** — EBITDA for direct-method filers (D&A in different sub-accounts). Currently falls back to EBIT with `ebitda_method="ebit_only"` provenance.
- **Restatement awareness** — `restated: true` flag when VERSAO > 1.

---

## 🚫 Deferred / Out of Scope

- **All 497 account codes** — `complete` mode returns key codes only (~30 codes across 5 grupos). Full hierarchy export deferred (too noisy for LLM context).
- **Historical restatements** — Currently keeps only the latest version (VERSAO dedup). Showing restated vs original is deferred.
- **Cross-company comparison** — ✅ Done (v1.0) — `skills/cvm/comparison` skill exists.

---

*Last updated: 2026-07-25 (v1.2).*
