<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.10** | 2026-08-01 | **EV/EBIT + DL/EBIT + CAGR + Margem EBIT alias.** Added 2 new metrics: `ev_ebit` (EV/EBIT — same pattern as ev_ebitda but denominator = EBIT instead of EBITDA, 5 engines: price+shares+debt+cash+ebit) and `dl_ebit` (DL/EBIT — same pattern as net_debt_ebitda but denominator = EBIT, 3 engines: debt+cash+ebit). Added CAGR functions to `growth_helpers.py`: `cagr_at(periods, target_date, years, max_gap_multiplier)` — compounded annualized rate `(end/start)^(1/years) - 1`, distinct from simple point-to-point growth. Added `cagr_history()` time series. Added `margem_ebit` alias to `operating_margin` metric (operating_margin IS Margem EBIT = EBIT/revenue). Total metrics: 55 → 57. No new engines needed. Inspired by LLM review of private spreadsheet (Claude 1 + Claude 2 both identified EV/EBIT and DL/EBIT as missing EBIT-denominator siblings). |
| **v1.9** | 2026-07-31 | **F7 engine cache (`@engine_cached` decorator + ContextVar scope).** Added `@engine_cached` decorator + `engine_cache_scope` context manager to `skills/_base.py`. Applied to all 34 engines' `at_fn` + `periods_fn` at module definition time. `compute_all_ratios()` wraps its loop in `with engine_cache_scope():` — engines shared across metrics (earnings used by 11 metrics, pl by 10, debt by 10, revenue by 15) are queried ONCE per `(company, date)` instead of N times. ~60% fewer DB queries per dashboard call. Thread-safe (ContextVar is per-thread + per-asyncio-task). Re-entrancy-safe (nested `compute_all_ratios()` reuses outer cache). Zero overhead when no scope active (passthrough). 17 new tests in `test_perf_infra.py`. |
| **v1.6** | 2026-07-30 | **9 new metrics inspired by private spreadsheet.** Added 5 per-share + price ratio metrics (rbpa — Resultado Bruto/Ação + P/RB, cgpa — Capital de Giro/Ação + P/CG, dbpa — Dívida Bruta/Ação + P/DB, apa — Ativo/Ação + P/Ativo, ppa — Passivo/Ação + P/Passivo), 2 valuation multiples (p_ebitda — P/EBITDA, p_ev — Price/Enterprise Value), and 2 leverage ratios (gross_debt_equity — Dívida Bruta/PL, financial_leverage — Ativo/PL). All include Portuguese aliases. Total metrics: 37 → 46. No new engines needed — all 9 metrics compose existing engines (price, shares, gross_profit, current_assets, current_liabilities, debt, total_assets, pl, ebit, da, cash). |
| **v1.5** | 2026-07-29 | **Registry-driven ratio computation.** Added `category` field to `MetricSpec` (8 categories: valuation, profitability, liquidity, leverage, efficiency, growth, per_share, tax). All 37 metrics tagged. Added `compute_all_ratios(company, date, categories=None, exclude=None)` — single entry point for consumer skills to get calculations-backed ratios without hardcoding imports. New metrics appear automatically everywhere via registration. Added `list_metric_categories()` + `list_metrics_by_category()` helpers. |
| **v1.4** | 2026-07-28 → 2026-07-29 | **v1.4 sprint — DVA rename + downstream wiring + financials migration + ROIC refactor + FCF_CODE + TTM regression test.** See "v1.4 Sprint Wrap-Up" section below for the full breakdown of all 6 work items in this sprint. Headline: (1) DVA engine prefix removal (4 engines renamed — see below); (2) ROIC delegates effective-tax-rate computation to `metrics.effective_tax_rate.effective_tax_rate_at` (was inlined as `tax/EBT`); (3) `engines/financing_cf.py` constant renamed `FF_CODE` → `FCF_CODE` (descriptive — FCF here is "Fluxo de Caixa de Financiamento" / Financing CF, NOT Free CF); (4) financials skill completed full migration to calculations engines (7 engine imports moved to module top-level in `metrics.py`; zero direct CVM queries remain in ratio computation); (5) new TTM regression test (`tests/skills/cvm/calculations/test_ttm_regression.py`) verifies TTM self-consistency against real CVM data for PETR4/KLBN11/SUZB3 (marked `@pytest.mark.slow`); (6) downstream wiring — valuation `ratios()` + `summary()` now expose the 15 v1.3 P2 metrics; comparison `_VALUATION_COLS` extended with 15 new columns; screener peer output extended with 9 new metrics. 31 engines + 37 metrics (unchanged from v1.3 — sprint was rename + wiring + refactor, no new engines/metrics). |
| **v1.3** | 2026-07-28 | **P2 sprint: 10 new engines + 15 new metrics.** New BPA engines: receivables (1.01.03), inventory (1.01.04), ppe (1.02.03), intangibles (1.02.04). New BPP engine: payables (2.01.01). New DRE engines: cogs (3.02), financial_result (3.06). New DVA category + 3 engines: dva_interest_paid (8.3), dva_total_tax (8.2), dva_value_added (7). New metrics (engines existed): ev_sales, ev_fcf, cash_ratio, ocf_margin, fcf_margin, working_capital, cash_flow_to_debt, retention_ratio, sustainable_growth. New metrics (new engines): quick_ratio, interest_coverage, inventory_turnover, receivables_turnover, fixed_asset_turnover, price_to_tangible_book. Now 30 engines + 37 metrics. |
| **v1.2** | 2026-07-28 | **Hardening: 5-review synthesis.** P0 correctness fixes: ROA + Asset Turnover repointed from `assets_at` (codigo 1.01, current assets) to `total_assets_at` (codigo 1, total assets) — was silently overstating both ratios ~2-5x; `assets.py` renamed → `current_assets.py` with correct function names. P1 new engines: EBT (3.07, with description-search fallback for banks/insurers) + Financing CF (6.03, FCF). P1 description-search fallback added to revenue/tax/earnings engines (ebit already had it). P1 ROIC formula corrected: `NOPAT = EBIT × (1 - tax/EBT)` (was `EBIT - tax_expense` approximation). P1 new metric: `effective_tax_rate` (tax/EBT, PT aliases: taxa_efetiva, aliquota_efetiva). P1 financials/metrics.py migrated to use calculations engines (2 new engine-backed functions). Test cleanup: deleted 5 duplicate/stale files, fixed test_p_fco.py copy-paste bug (was testing p_ebit), filled test_p_ebit.py + test_p_fcf.py empty stubs. Now 20 engines + 22 metrics. ROADMAP.md added documenting P2/P3 deferred items. |
| **v1.1** | 2026-07-28 | **Test rename + count fix.** Renamed `test_tier4_metrics.py` → `test_fundamental_ratios.py` and `test_tier56_metrics.py` → `test_capex_current_ratio.py` (descriptive names — no version numbers in filenames). Fixed stale count assertions: `test_total_engines_is_16`/`test_total_metrics_is_17` → `test_engine_count`/`test_metric_count` with `>= 18`/`>= 21` floor assertions (no hardcoded numbers in test names; future additions won't break them). Updated 7 architecture docs (16→18 engines, 17→21 metrics, 6→7 categories, 5→8 per-share+ratio, 12→13 fundamental). EBIT engine gained description-search fallback for non-standard DRE filers (banks/insurers). da/capex engines scoped to correct DFC sections (6.01/6.02) + accent-normalized exclusion of financing/disposal lines. |
| **v1.0** | 2026-07-26 | **Extracted from historical v2.1.** 16 engines + 17 metrics + central `_registry.py` moved from `skills/cvm/historical/` to `skills/cvm/calculations/`. All import paths updated. Historical skill now imports from calculations. This is the shared foundation for all CVM skills — valuation, financials, and future backtest will import from here. 355 tests pass. |

---

## 📦 v1.4 Sprint Wrap-Up

The v1.4 sprint was a multi-work-item effort covering engine renames, downstream wiring, and cross-skill migration. Six work items landed:

### 1. DVA engine prefix removal (2026-07-28)

The 4 DVA-category engines had a `dva_` prefix in their engine name, function names, constant names, and file names — no other engine category uses a prefix (e.g., `revenue` not `dre_revenue`, `ebit` not `dre_ebit`, `debt` not `bpp_debt`). Removed the prefix to follow the naming convention.

| Before | After | CVM code |
|--------|-------|----------|
| `dva_dividends_paid` | `dividends_paid` | DVA 8.4 |
| `dva_interest_paid` | `interest_paid` | DVA 8.3 |
| `dva_total_tax` | `total_tax` | DVA 8.2 |
| `dva_value_added` | `value_added` | DVA 7 |

- Quantity keys renamed: `ttm_dva_dividends` → `ttm_dividends_paid`, `ttm_dva_interest` → `ttm_interest_paid`, `ttm_dva_tax` → `ttm_total_tax`, `ttm_dva_va` → `ttm_value_added`.
- Code constants renamed: `DVA_DIVIDENDS_PAID_CODE` → `DIVIDENDS_PAID_CODE` (and likewise for the other 3).
- Internal helpers renamed: `_get_dfp_dva_*` → `_get_dfp_*`, `_get_itr_dva_*` → `_get_itr_*`.
- File + test renames: `engines/dva_*.py` → `engines/*.py`, `tests/.../test_dva_*.py` → `tests/.../test_*.py`.
- Preserved as-is: `DVA_GRUPO = "DVA"` (DB group identifier), `category="dva"` (organizational grouping), SQL filter `AND c.grupo = 'DVA'`.

### 2. ROIC delegates effective-tax-rate to `effective_tax_rate_at` (2026-07-29)

The v1.2 ROIC fix corrected the NOPAT formula from `EBIT - tax_expense` to `EBIT × (1 - tax/EBT)` but inlined the effective-tax-rate computation. v1.4 refactored this to delegate to the standalone `metrics.effective_tax_rate.effective_tax_rate_at` metric (added in v1.2): `effective_tax_rate = effective_tax_rate_at(company, date)` (clamped to `[0, 0.50]` — max 50% for Brazil's combined IRPJ+CSLL rate). This eliminates the duplicated `tax/EBT` inline logic in `roic.py` + `roic_history()` and ensures ROIC's effective-tax-rate computation stays in lockstep with the standalone metric. The `engines` list in the `MetricSpec` for `roic` is unchanged (`["ebit", "tax", "ebt", "pl", "debt", "cash"]`).

### 3. `financing_cf.py` constant renamed `FF_CODE` → `FCF_CODE` (2026-07-29)

`engines/financing_cf.py` previously used a generic `FF_CODE = "6.03"` constant. Renamed to `FCF_CODE` to be descriptive — FCF here is "Fluxo de Caixa de Financiamento" (Financing Cash Flow), NOT "Free Cash Flow". The quantity key remains `ttm_fcf` (mirrors the engine name `financing_cf`). The module docstring's "NOTE: FCF here is Financing CF, not Free CF" warning is preserved — callers must remember this distinction. Free CF is composed elsewhere as `FCO + FCI` (see `metrics/p_fcf.py`).

### 4. Financials skill full migration to calculations engines (2026-07-29)

`skills/cvm/financials/metrics.py` previously had engine imports as LAZY (inside function bodies of `compute_ebitda_from_engines` + `compute_ttm_with_engines`, the v1.3 engine-backed variants). v1.4 moved all 7 engine imports to module top-level in a `[v1.4-financials-migration]` comment block:
- `ebit_at`, `da_at` (for `compute_ebitda_from_engines`)
- `revenue_at`, `ebit_at`, `da_at`, `ttm_earnings_at`, `operating_cf_at`, `investing_cf_at`, `financing_cf_at` (for `compute_ttm_with_engines`)

Net effect: zero direct CVM queries (no `connect_dfp`/`connect_itr`/`SELECT...FROM`/`codigo=...`) remain in any ratio computation function — every flow metric goes through the calculations engines. This brings the v1.2 hardening (description-search fallback for EBIT at codigo 3.05; section-scoped 6.01.* for D&A) into financials automatically — the engines own that logic. See [financials CHANGELOG](../financials/CHANGELOG.md) v1.4 for full details.

### 5. TTM regression test (2026-07-29)

New test file: `tests/skills/cvm/calculations/test_ttm_regression.py`. Verifies TTM derivation self-consistency against real CVM data (PETR4, KLBN11, SUZB3):

1. **TTM revenue/EBIT/earnings are positive** for profitable companies (parametrized over the 3 tickers + 3 engines: `revenue_at`, `ebit_at`, `ttm_earnings_at`).
2. **TTM operating_cf + investing_cf are computable** (positive for cash-generating companies).
3. **TTM self-consistency**: TTM at a date after the annual DFP filing (e.g., 2024-03-31) uses `DFP[2023] - ITR[2023][Q1] + ITR[2024][Q1]` — verifies the formula lands in plausible ranges vs. the annual DFP value.

Test is marked `@pytest.mark.slow` (requires real CVM databases — DFP + ITR synced). Run with `python -m pytest -m slow -v`. Not in the default test run.

### 6. Downstream wiring — valuation + comparison + screener (2026-07-29)

The v1.3 P2 sprint added 15 new calculations metrics but they were not surfaced in the downstream skills. v1.4 wired them in:

- **valuation** — `ratios()` extended with a `v13_new_metrics` loop using `_safe_call(fn, ticker, today)`; `summary()` extended with a `headline_v13_metrics` block (10 most important new metrics at the top level). See [valuation CHANGELOG](../valuation/CHANGELOG.md) v1.4.
- **comparison** — `_VALUATION_COLS` extended with 15 new `(label, dict_key, spec)` entries grouped by family. Comparison picks them up transitively via `valuation.ratios()` (no new data fetching). See [comparison CHANGELOG](../comparison/CHANGELOG.md) v1.4.
- **screener** — peer dict + medians dict + comparison dict extended with 9 of the 15 new metrics (the most useful for peer comparison: EV/Sales, EV/FCF, Quick Ratio, Cash Ratio, OCF Margin, FCF Margin, Cash Flow to Debt, Interest Coverage, Sustainable Growth). See [screener CHANGELOG](../screener/CHANGELOG.md) v1.4.

---

*Last updated: 2026-07-29 (v1.5 — registry-driven ratio computation).*
