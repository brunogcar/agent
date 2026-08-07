<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/_base.py` | **Shared skill infrastructure** — ModeSpec + make_registry + make_route + auto_discover_modes + **[v1.8] `@engine_cached` decorator + `engine_cache_scope`** |
| `skills/cvm/calculations/_registry.py` | **Central registry** — EngineSpec + MetricSpec + auto-discovery for both engines/ and metrics/ + `compute_all_ratios()` (wraps loop in `engine_cache_scope()`) |
| `skills/cvm/calculations/engines/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/calculations/engines/price.py` | COTAHIST daily close: `price_at()`, `price_series()` |
| `skills/cvm/calculations/engines/dre/earnings.py` | TTM earnings: `ttm_earnings_at()`, `ttm_earnings_periods()` |
| `skills/cvm/calculations/engines/shares.py` | FRE shares (+ investsite fallback): `shares_at()`, `shares_periods()` |
| `skills/cvm/calculations/engines/bpp/pl.py` | PL snapshot (BPP 2.03): `pl_at()`, `pl_periods()` |
| `skills/cvm/calculations/engines/dividends.py` | DPA TTM (B3 cash_dividends): `dividends_at()`, `dividends_periods()` |
| `skills/cvm/calculations/engines/dre/revenue.py` | TTM revenue (DRE 3.01): `revenue_at()`, `revenue_periods()` |
| `skills/cvm/calculations/engines/dre/gross_profit.py` | TTM gross profit (DRE 3.03): `gross_profit_at()`, `gross_profit_periods()` |
| `skills/cvm/calculations/engines/dre/ebit.py` | TTM EBIT (DRE 3.05): `ebit_at()`, `ebit_periods()` |
| `skills/cvm/calculations/engines/dre/ebt.py` | TTM EBT (DRE 3.07, with description-search fallback): `ebt_at()`, `ebt_periods()` |
| `skills/cvm/calculations/engines/dre/tax.py` | TTM income tax (DRE 3.08): `tax_at()`, `tax_periods()` |
| `skills/cvm/calculations/engines/dre/cogs.py` | TTM COGS (DRE 3.02): `cogs_at()`, `cogs_periods()` |
| `skills/cvm/calculations/engines/dre/financial_result.py` | TTM financial result (DRE 3.06, net): `financial_result_at()`, `financial_result_periods()` |
| `skills/cvm/calculations/engines/bpa/current_assets.py` | Current assets snapshot (BPA 1.01): `current_assets_at()`, `current_assets_periods()` |
| `skills/cvm/calculations/engines/bpa/cash.py` | Cash snapshot (BPA 1.01.01): `cash_at()`, `cash_periods()` |
| `skills/cvm/calculations/engines/bpa/total_assets.py` | Total assets snapshot (BPA 1): `total_assets_at()`, `total_assets_periods()` |
| `skills/cvm/calculations/engines/bpa/receivables.py` | Receivables snapshot (BPA 1.01.03): `receivables_at()`, `receivables_periods()` |
| `skills/cvm/calculations/engines/bpa/inventory.py` | Inventory snapshot (BPA 1.01.04): `inventory_at()`, `inventory_periods()` |
| `skills/cvm/calculations/engines/bpa/ppe.py` | PP&E snapshot (BPA 1.02.03): `ppe_at()`, `ppe_periods()` |
| `skills/cvm/calculations/engines/bpa/intangibles.py` | Intangibles snapshot (BPA 1.02.04): `intangibles_at()`, `intangibles_periods()` |
| `skills/cvm/calculations/engines/bpp/debt.py` | Debt snapshot (BPP 2.01.04+2.02.01, sum): `debt_at()`, `debt_periods()` |
| `skills/cvm/calculations/engines/bpp/current_liabilities.py` | Current liabilities snapshot (BPP 2.01): `current_liabilities_at()`, `current_liabilities_periods()` |
| `skills/cvm/calculations/engines/bpp/payables.py` | Payables snapshot (BPP 2.01.01): `payables_at()`, `payables_periods()` |
| `skills/cvm/calculations/engines/dfc/da.py` | D&A TTM (DFC description search): `da_at()`, `da_periods()` |
| `skills/cvm/calculations/engines/dfc/capex.py` | CapEx TTM (DFC description search): `capex_at()`, `capex_periods()` |
| `skills/cvm/calculations/engines/dfc/operating_cf.py` | TTM operating cash flow (DFC 6.01): `operating_cf_at()`, `operating_cf_periods()` |
| `skills/cvm/calculations/engines/dfc/investing_cf.py` | TTM investing cash flow (DFC 6.02): `investing_cf_at()`, `investing_cf_periods()` |
| `skills/cvm/calculations/engines/dfc/financing_cf.py` | TTM financing cash flow (DFC 6.03): `financing_cf_at()`, `financing_cf_periods()` |
| `skills/cvm/calculations/engines/interest_paid.py` | TTM interest paid (DVA grupo='DVA' codigo 8.3): `interest_paid_at()`, `interest_paid_periods()` |
| `skills/cvm/calculations/engines/total_tax.py` | TTM total tax burden (DVA grupo='DVA' codigo 8.2): `total_tax_at()`, `total_tax_periods()` |
| `skills/cvm/calculations/engines/value_added.py` | TTM total value added (DVA grupo='DVA' codigo 7): `value_added_at()`, `value_added_periods()` |
| `skills/cvm/calculations/metrics/__init__.py` | Minimal docstring |
| `skills/cvm/calculations/metrics/lpa.py` | LPA + P/L: `lpa_at()`, `pe_at()`, `lpa_history()` |
| `skills/cvm/calculations/metrics/vpa.py` | VPA + P/VPA: `vpa_at()`, `pvpa_at()`, `vpa_history()` |
| `skills/cvm/calculations/metrics/dpa.py` | DPA + DY + Payout: `dpa_at()`, `dy_at()`, `payout_at()`, `dpa_history()` |
| `skills/cvm/calculations/metrics/rps.py` | RPS + PSR: `rps_at()`, `psr_at()`, `rps_history()` |
| `skills/cvm/calculations/metrics/ev_ebitda.py` | EBITDA/share + EV/EBITDA: `ebitda_ps_at()`, `ev_ebitda_at()`, `ev_ebitda_history()` |
| `skills/cvm/calculations/metrics/p_ebit.py` | EBIT/share + P/EBIT: `ebit_ps_at()`, `p_ebit_at()`, `p_ebit_history()` |
| `skills/cvm/calculations/metrics/p_fco.py` | FCO/share + P/FCO: `fco_ps_at()`, `p_fco_at()`, `p_fco_history()` |
| `skills/cvm/calculations/metrics/p_fcf.py` | FCF/share + P/FCF: `fcf_ps_at()`, `p_fcf_at()`, `p_fcf_history()` |
| `skills/cvm/calculations/metrics/roe.py` | ROE (fundamental): `roe_at()`, `roe_history()` |
| `skills/cvm/calculations/metrics/roa.py` | ROA (fundamental): `roa_at()`, `roa_history()` |
| `skills/cvm/calculations/metrics/roic.py` | ROIC (fundamental): `roic_at()`, `roic_history()` |
| `skills/cvm/calculations/metrics/gross_margin.py` | Margem Bruta (fundamental): `gross_margin_at()`, `gross_margin_history()` |
| `skills/cvm/calculations/metrics/operating_margin.py` | Margem Operacional (fundamental): `operating_margin_at()`, `operating_margin_history()` |
| `skills/cvm/calculations/metrics/net_margin.py` | Margem Líquida (fundamental): `net_margin_at()`, `net_margin_history()` |
| `skills/cvm/calculations/metrics/ebitda_margin.py` | Margem EBITDA (fundamental): `ebitda_margin_at()`, `ebitda_margin_history()` |
| `skills/cvm/calculations/metrics/debt_equity.py` | Dívida/PL (fundamental): `debt_equity_at()`, `debt_equity_history()` |
| `skills/cvm/calculations/metrics/net_debt_ebitda.py` | DL/EBITDA (fundamental): `net_debt_ebitda_at()`, `net_debt_ebitda_history()` |
| `skills/cvm/calculations/metrics/asset_turnover.py` | Giro de Ativos (fundamental): `asset_turnover_at()`, `asset_turnover_history()` |
| `skills/cvm/calculations/metrics/capex_revenue.py` | CapEx/Receita (fundamental): `capex_revenue_at()`, `capex_revenue_history()` |
| `skills/cvm/calculations/metrics/current_ratio.py` | Liquidez Corrente (fundamental): `current_ratio_at()`, `current_ratio_history()` |
| `skills/cvm/calculations/metrics/graham_number.py` | Graham Number (fundamental): `graham_number_at()`, `graham_number_history()` |
| `skills/cvm/calculations/metrics/effective_tax_rate.py` | Taxa Efetiva (fundamental): `effective_tax_rate_at()`, `effective_tax_rate_history()` |
| `skills/cvm/calculations/metrics/price_to_tangible_book.py` | Tangible Book/share + P/Tangible Book (Type 1, v1.3): `tangible_book_ps_at()`, `p_tangible_book_at()`, `price_to_tangible_book_history()` |
| `skills/cvm/calculations/metrics/ev_sales.py` | EV/Sales (fundamental, v1.3): `ev_sales_at()`, `ev_sales_history()` |
| `skills/cvm/calculations/metrics/ev_fcf.py` | EV/FCF (fundamental, v1.3): `ev_fcf_at()`, `ev_fcf_history()` |
| `skills/cvm/calculations/metrics/cash_ratio.py` | Cash Ratio (fundamental, v1.3): `cash_ratio_at()`, `cash_ratio_history()` |
| `skills/cvm/calculations/metrics/ocf_margin.py` | OCF Margin (fundamental, v1.3): `ocf_margin_at()`, `ocf_margin_history()` |
| `skills/cvm/calculations/metrics/fcf_margin.py` | FCF Margin (fundamental, v1.3): `fcf_margin_at()`, `fcf_margin_history()` |
| `skills/cvm/calculations/metrics/working_capital.py` | Working Capital (fundamental, BRL value, v1.3): `working_capital_at()`, `working_capital_history()` |
| `skills/cvm/calculations/metrics/cash_flow_to_debt.py` | Cash Flow to Debt (fundamental, v1.3): `cash_flow_to_debt_at()`, `cash_flow_to_debt_history()` |
| `skills/cvm/calculations/metrics/retention_ratio.py` | Retention Ratio (fundamental, v1.3): `retention_ratio_at()`, `retention_ratio_history()` |
| `skills/cvm/calculations/metrics/sustainable_growth.py` | Sustainable Growth Rate (fundamental, composes metrics, v1.3): `sustainable_growth_at()`, `sustainable_growth_history()` |
| `skills/cvm/calculations/metrics/quick_ratio.py` | Quick Ratio (fundamental, v1.3): `quick_ratio_at()`, `quick_ratio_history()` |
| `skills/cvm/calculations/metrics/interest_coverage.py` | Interest Coverage (fundamental, v1.3 approximation): `interest_coverage_at()`, `interest_coverage_history()` |
| `skills/cvm/calculations/metrics/inventory_turnover.py` | Inventory Turnover (fundamental, v1.3): `inventory_turnover_at()`, `inventory_turnover_history()` |
| `skills/cvm/calculations/metrics/receivables_turnover.py` | Receivables Turnover (fundamental, v1.3): `receivables_turnover_at()`, `receivables_turnover_history()` |
| `skills/cvm/calculations/metrics/fixed_asset_turnover.py` | Fixed Asset Turnover (fundamental, v1.3): `fixed_asset_turnover_at()`, `fixed_asset_turnover_history()` |

---

## 🧱 Engine vs Metric — The Core Pattern

Engines are leaves (one per raw quantity, fetch from data sources). Metrics compose engines (one per ratio). Both self-register. See historical ARCHITECTURE.md for the full pattern documentation — it's the same.

### Engine inventory by category (30 engines, 7 categories):

| Category | Engines |
|----------|---------|
| market | price, dividends |
| shares | shares |
| dre | earnings, revenue, gross_profit, ebit, ebt, tax, cogs, financial_result |
| bpa | current_assets, cash, total_assets, receivables, inventory, ppe, intangibles |
| bpp | pl, debt, current_liabilities, payables |
| dfc | da, capex, operating_cf, investing_cf, financing_cf |
| dva | interest_paid, total_tax, value_added |

### Metric inventory by type (55 metrics):

| Type | Metrics |
|------|---------|
| Per-share + price ratio | lpa (LPA+P/L), vpa (VPA+P/VPA), dpa (DPA+DY+Payout), rps (RPS+PSR), ev_ebitda (EBITDA/share+EV/EBITDA), p_ebit (EBIT/share+P/EBIT), p_fco (FCO/share+P/FCO), p_fcf (FCF/share+P/FCF), price_to_tangible_book (Tangible Book/share+P/Tangible Book), rbpa (RBPA+P/RB), cgpa (CGPA+P/CG), dbpa (DBPA+P/DB), apa (APA+P/Ativo), ppa (PPA+P/Passivo), p_ebitda (EBITDA/share+P/EBITDA) |
| Fundamental ratio | roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin, debt_equity, gross_debt_equity, financial_leverage, net_debt_ebitda, asset_turnover, capex_revenue, current_ratio, graham_number, effective_tax_rate, ev_sales, ev_fcf, cash_ratio, ocf_margin, fcf_margin, working_capital, cash_flow_to_debt, retention_ratio, sustainable_growth, quick_ratio, interest_coverage, inventory_turnover, receivables_turnover, fixed_asset_turnover |
| Pure price ratio (no per-share) | p_ev (Price/EV) |

### Metric inventory by category (v1.7 — 8 categories, 55 metrics tagged):

| Category | Metrics |
|----------|---------|
| `valuation` | lpa, vpa, dpa, rps, ev_ebitda, p_ebit, p_fco, p_fcf, price_to_tangible_book, ev_sales, ev_fcf, graham_number, p_ebitda, p_ev |
| `profitability` | roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin |
| `liquidity` | current_ratio, cash_ratio, quick_ratio, working_capital |
| `leverage` | debt_equity, gross_debt_equity, financial_leverage, net_debt_ebitda, cash_flow_to_debt, interest_coverage |
| `efficiency` | asset_turnover, capex_revenue, inventory_turnover, receivables_turnover, fixed_asset_turnover |
| `growth` | retention_ratio, sustainable_growth, revenue_growth_3m, revenue_growth_1y, revenue_growth_5y, gross_profit_growth_3m, gross_profit_growth_1y, gross_profit_growth_5y, net_income_growth_3m, net_income_growth_1y, net_income_growth_5y |
| `per_share` | lpa, vpa, dpa, rps, ebitda_ps, ebit_ps, fco_ps, fcf_ps, tangible_book_ps, rbpa, cgpa, dbpa, apa, ppa (per-share quantities surfaced by Type 1 metrics) |
| `tax` | effective_tax_rate |

Use `list_metric_categories()` to enumerate at runtime and `list_metrics_by_category("liquidity")` to list the metrics in a category. `compute_all_ratios(company, date, categories=["liquidity", "leverage"])` returns only the metrics in the requested categories.

---

## 🔀 Dependency Graph

```
calculations/
├── _registry.py  (EngineSpec + MetricSpec + auto-discovery)
│
├── engines/  (leaves — never import each other or metrics)
│   ├── price.py → COTAHIST
│   ├── earnings.py → DFP+ITR (TTM)
│   ├── shares.py → FRE+investsite
│   ├── pl.py → DFP+ITR BPP 2.03 (snapshot)
│   ├── ... (26 more engines)
│
└── metrics/  (compose engines)
    ├── lpa.py → price + earnings + shares
    ├── roe.py → earnings + pl
    ├── ev_ebitda.py → price + shares + debt + cash + ebit + da
    ├── roic.py → ebit + tax + ebt + pl + debt + cash (v2.0 EBT-based NOPAT)
    ├── effective_tax_rate.py → tax + ebt
    └── ... (32 more metrics)

         ↓ imported by

skills/cvm/historical/  (mode dispatch + percentile analysis)
skills/cvm/valuation/   (Phase 2: will refactor to use calculations)
skills/cvm/financials/  (Phase 3: will refactor to use calculations)
skills/cvm/backtest/    (Phase 4: future, will use calculations)
```

---

## 🤖 Central Auto-Discovery

`_registry.py` at the top level globs both `engines/*.py` and `metrics/*.py`, imports each via `importlib`. Each engine/metric self-registers at import time. Adding a new engine/metric = drop a file + `register_*()`. Zero edits to `__init__.py` files.

---

---

## 🔄 Force Sync Guard (v1.14)

When a user calls a skill via `route()`, the sync guard checks if the
required data sources are fresh (synced within 24h). If stale, it
force-syncs them BEFORE dispatching to the mode function.

**This is NOT auto-sync (cron).** It's on-demand when a skill is used.
The first call of the day may take 30+ seconds (DFP sync); subsequent
calls within 24h are fast.

**Components (all in `skills/_base.py`):**
- `ensure_fresh(sources, company, skip_sync, trace_id)` — main entry point
- `_source_is_stale(source)` — reads `sync_state` timestamp, checks 24h window
- `_cvm_has_new_data(source, year)` — HEAD request to CVM URL, compares
  `Last-Modified` header to last sync. Timeout=5s. On network error → sync.
- `_trigger_sync(source, company, trace_id)` — maps source name to sync fn
  with right args (current-year-only `force=True`, ticker-only for bridge)
- `_SYNC_CHECKED` ContextVar — re-entrancy guard (nested route calls run
  ensure_fresh at most once)
- `_route_with_sync_guard()` — wraps sync check + dispatch in the guard

**Force-sync args by source:**
- DFP/ITR/FRE/IPE: `sync(years=[current_year], force=True)`
- FCA/VLMO/CGVN: `sync(year=current_year, force=True)`
- CAD: `sync(force=True)`
- bridge: `sync(ticker=<company>, force=True)` — only requested ticker
- cotahist: `sync(year=current_year, force=True)`
- brapi: `sync_tickers(force=True)`

**Escape hatches:**
- `CVM_SKIP_SYNC=1` env var (set in `tests/skills/cvm/conftest.py` for all tests)
- `route(..., skip_sync=True)` per-call kwarg

**Failure path:** If sync fails, the skill proceeds with stale data + the
error is recorded in `result["_sync"]["errors"]`. Stale-but-available is
better than no answer for dashboards.

---

## ⚡ Engine Cache (v1.8 F7)

All 34 engines are decorated with `@engine_cached` (from `skills._base`) at
module definition time. The decorator uses a `ContextVar`-scoped dict to
cache results within a `compute_all_ratios()` call.

**Why:** 49 metrics compose 34 engines, but many engines are shared —
`earnings` is used by 11 metrics, `pl` by 10, `debt` by 10, `revenue` by 15.
Without caching, a single `compute_all_ratios()` call fires ~90 engine
queries, ~60% redundant (same engine, same company, same date). With the
cache, each engine is queried ONCE per `(company, date)` → ~60% fewer DB
queries.

**How it works:**
1. `@engine_cached` is applied to `at_fn` + `periods_fn` in each engine file
   (at definition time, before any metric imports the function).
2. The decorator checks `_ENGINE_CACHE` ContextVar; if `None` (no scope
   active), it's a passthrough (zero overhead for standalone calls).
3. `compute_all_ratios()` wraps its loop in `with engine_cache_scope():`
   to activate the cache.
4. Cache key: `(fn.__name__, company, str(date))` for `at_fn`;
   `(fn.__name__, company)` for `periods_fn`.
5. `None` values ARE cached (prevents re-querying missing data).

**Why decorator (not monkey-patch):** Metrics use
`from engines.earnings import ttm_earnings_at` — a direct reference bound
at import time. Monkey-patching the module attribute after import is
invisible to metrics. The decorator is applied at definition time, so
`spec.at_fn` and `module.fn` are the same wrapper object, permanently.

**Thread safety:** `ContextVar` is per-thread + per-asyncio-task. No lock
needed. **Reentrancy:** Nested `compute_all_ratios()` calls reuse the outer
scope's cache (the inner `engine_cache_scope.__enter__` detects an active
scope and doesn't install a new one).

---

## 📐 Key Design Patterns

1. **Central `_registry.py`** — single source of truth for auto-discovery
2. **Engine categories** — `list_engines(category="dre")` for filtering
3. **Metric categories (v1.5)** — `list_metric_categories()` + `list_metrics_by_category("liquidity")` for filtering; `compute_all_ratios(company, date, categories=[...], exclude=[...])` is the single entry point for consumer skills
4. **TTM derivation** — DFP_prior - ITR_prior_same + ITR_current (flow engines)
5. **Snapshot lookup** — most recent BPP/BPA snapshot <= date (balance engines)
6. **Description-based search** — da + capex search DFC by descricao keywords
7. **Multi-code sum** — debt sums BPP 2.01.04 + 2.02.01
8. **[v1.8] Engine cache** — `@engine_cached` decorator + `engine_cache_scope()` ContextVar; engines shared across metrics are queried ONCE per (company, date)
9. **Step-function optimization** — precompute periods, O(1) lookups per day
10. **Flexible MetricSpec** — per_share fields optional for fundamental ratios; `category` field (v1.5) for filtered discovery
11. **PT + EN aliases** on all metrics
12. **Idempotent auto-discovery** — `_done` flag prevents re-registration

---

*Last updated: 2026-08-07 (v1.17))) — force sync guard). See [API.md](API.md) for function signatures, [ROADMAP.md](ROADMAP.md) for deferred items, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
