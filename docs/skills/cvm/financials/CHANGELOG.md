<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.5** | 2026-07-29 | **Registry-driven ratios + dashboard mode + data freshness.** `summary()` now uses `compute_all_ratios()` (25 metrics auto-discovered, was 6 hardcoded). New `dashboard()` mode — 5-tab thin composition (Overview/DRE/Balanço/DFC/Ratios) optimized for report tool's dashboard action. `last_synced_period` added to data freshness (MAX(data_fim_exerc) from DFP+ITR). |
| **v1.4** | 2026-07-29 | **Full migration to calculations engines.** The v1.3 work introduced two engine-backed variants (`compute_ebitda_from_engines`, `compute_ttm_with_engines`) but kept their engine imports LAZY (inside function bodies, not at module top). v1.4 completes the migration: all 7 engine imports (`ebit_at`, `da_at`, `revenue_at`, `ttm_earnings_at`, `operating_cf_at`, `investing_cf_at`, `financing_cf_at`) moved to module top-level in a `[v1.4-financials-migration]` block, making the dependency explicit + mockable as `skills.cvm.financials.metrics.<fn>_at`. Net effect: zero direct CVM queries (no `connect_dfp`/`connect_itr`/`SELECT...FROM`/`codigo=...`) remain in any ratio computation function — every flow metric goes through the calculations engines. This brings the v1.2 hardening (description-search fallback for EBIT at codigo 3.05; section-scoped 6.01.* for D&A) into financials automatically — the engines own that logic. Public API unchanged (`compute_ratios`, `compute_ebitda`, `compute_ttm`, `compute_ebitda_from_engines`, `compute_ttm_with_engines` all preserved). Snapshot metrics (ativo_total, caixa, patrimonio_liquido, divida_bruta) continue to use 4-quarter averaging from the periods list (calculations engines return point-in-time snapshots, semantically different from financials' averaging approach). Statement-rendering modes (`quarterly`, `annual`, `complete`) unchanged — they operate on raw `{codigo: valor}` dicts per period, not point-in-time engine snapshots. Quarterly ROA/ROE ×4 annualization preserved (period semantics differ from TTM-based calculations metrics — flagged as a known TODO). 80/80 financials tests pass with `-W error`. |
| **v1.3** | 2026-07-27 | **Phase 3: Calculations integration + tests split.** `summary()` mode now delegates point-in-time ratios (ROIC, Graham Number, EV/EBITDA, P/FCF, P/EBIT, P/FCO) to `skills.cvm.calculations.metrics.*` via lazy imports wrapped in `_safe_call` (returns None on missing DB / missing account). New `current_ratios` section complements (does not replace) the per-period `latest_annual` + `latest_quarterly` sections. Statement-rendering modes (`quarterly`, `annual`, `complete`) and `metrics.py` (`compute_ratios`, `compute_ebitda`, `compute_ttm`) are UNCHANGED — they operate on raw statement dicts per period, not point-in-time engine snapshots, so calculations engines cannot replace them. Single 595-line `test_financials.py` split into `conftest.py` + 6 per-mode test files (metrics / annual / quarterly / complete / summary / route). 1 new test for `current_ratios` (37 total, up from 36). |
| v1.2 | 2026-07-25 | **DFC_MD filer support.** Added D&A fallback codes for direct-method DFC filers (DFC_MD). _extract_metrics now tries 6.01.01.02 (DFC_MI indirect) first, then 6.02.01.02 + 6.01.04 (DFC_MD direct). EBITDA for direct-method filers now uses real D&A instead of falling back to ebit_only. 5 new tests. |
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
- **DFC_MD filer support** — ✅ v1.2 (was roadmap item). _extract_metrics now falls back to DFC_MD codes for direct-method filers.
- **Calculations integration (summary mode)** — ✅ v1.3. `summary()` delegates ROIC, Graham, EV/EBITDA, P/FCF, P/EBIT, P/FCO to `skills.cvm.calculations.metrics.*`.
- **Full calculations migration (metrics.py)** — ✅ v1.4. All 7 engine imports moved to module top-level; zero direct CVM queries remain in ratio computation.

---

### ⚠️ Breaking Changes

*(None in v1.4 — additive only. The 7 engine imports move from function-body lazy imports to module top-level imports; this changes the import-time side effect (importing `metrics.py` now triggers calculations auto-discovery, which requires `PLANNER_MODEL` to be set in the env). All public functions (`compute_ratios`, `compute_ebitda`, `compute_ttm`, `compute_ebitda_from_engines`, `compute_ttm_with_engines`) preserve their signatures. Callers that already imported `metrics.py` in a context where `PLANNER_MODEL` is set (e.g., the financials skill itself, which sets it via conftest) are unaffected.)*

*(None in v1.3 — additive only. The new `current_ratios` section is added to the `summary()` response; existing `latest_annual`, `latest_quarterly`, `quarterly_trend` sections are unchanged. Consumers that read only those keys are unaffected.)*

---

## 🔄 In Progress / Next Up

- **Average balance sheet for ROA/ROE** — Rapinav2 averages balance-sheet values for TTM/annual ratio denominators. TTM now uses average of 4 (v1.1), but annual still uses period-end.
- **Individual (non-consolidated)** — Already supported via `consolidado=0` but needs testing with real data.
- **IPCA inflation adjustment** — Normalize historical BRL to present value for multi-year comparisons.
- **Sector benchmarks** — Compute sector medians (P/L, EV/EBITDA, ROE by sector) by aggregating financials across companies.
- **QoQ growth** — Quarter-over-quarter % change. Now available via `comparison` skill `growth` mode.
- **Data freshness indicator** — Expose `last_sync_at` in responses so consumers know data age.
- **Restatement awareness** — `restated: true` flag when VERSAO > 1.
- **Deeper calculations integration** — ✅ v1.4 (was roadmap item). `metrics.py` engine-backed variants now use top-level imports; zero direct CVM queries remain in ratio computation. Future: surface calculations metrics inside `quarterly` + `annual` period entries (e.g., ROIC per period). Currently these modes keep their own `compute_ratios()` because calculations engines are point-in-time, not per-period.

---

## 🚫 Deferred / Out of Scope

- **All 497 account codes** — `complete` mode returns key codes only (~30 codes across 5 grupos). Full hierarchy export deferred (too noisy for LLM context).
- **Historical restatements** — Currently keeps only the latest version (VERSAO dedup). Showing restated vs original is deferred.
- **Cross-company comparison** — ✅ Done (v1.0) — `skills/cvm/comparison` skill exists.
- **Replacing `compute_ratios()` with calculations metrics in quarterly/annual modes** — Calculations engines are point-in-time (`*_at(company, date)`) and not designed to render per-period ratios from raw statement dicts. The two patterns serve different purposes (statement rendering vs current snapshot) and coexist intentionally.

---

*Last updated: 2026-07-29 (v1.5).*
