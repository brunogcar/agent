<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/calculations/_registry.py` | **Central registry** — EngineSpec + MetricSpec + auto-discovery for both engines/ and metrics/ |
| `skills/cvm/calculations/engines/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/calculations/engines/price.py` | COTAHIST daily close: `price_at()`, `price_series()` |
| `skills/cvm/calculations/engines/earnings.py` | TTM earnings: `ttm_earnings_at()`, `ttm_earnings_periods()` |
| `skills/cvm/calculations/engines/shares.py` | FRE shares (+ investsite fallback): `shares_at()`, `shares_periods()` |
| `skills/cvm/calculations/engines/pl.py` | PL snapshot (BPP 2.03): `pl_at()`, `pl_periods()` |
| `skills/cvm/calculations/engines/dividends.py` | DPA TTM (B3 cash_dividends): `dividends_at()`, `dividends_periods()` |
| `skills/cvm/calculations/engines/revenue.py` | TTM revenue (DRE 3.01): `revenue_at()`, `revenue_periods()` |
| `skills/cvm/calculations/engines/gross_profit.py` | TTM gross profit (DRE 3.03): `gross_profit_at()`, `gross_profit_periods()` |
| `skills/cvm/calculations/engines/ebit.py` | TTM EBIT (DRE 3.05): `ebit_at()`, `ebit_periods()` |
| `skills/cvm/calculations/engines/ebt.py` | TTM EBT (DRE 3.07, with description-search fallback): `ebt_at()`, `ebt_periods()` |
| `skills/cvm/calculations/engines/tax.py` | TTM income tax (DRE 3.08): `tax_at()`, `tax_periods()` |
| `skills/cvm/calculations/engines/current_assets.py` | Current assets snapshot (BPA 1.01): `current_assets_at()`, `current_assets_periods()` |
| `skills/cvm/calculations/engines/cash.py` | Cash snapshot (BPA 1.01.01): `cash_at()`, `cash_periods()` |
| `skills/cvm/calculations/engines/total_assets.py` | Total assets snapshot (BPA 1): `total_assets_at()`, `total_assets_periods()` |
| `skills/cvm/calculations/engines/debt.py` | Debt snapshot (BPP 2.01.04+2.02.01, sum): `debt_at()`, `debt_periods()` |
| `skills/cvm/calculations/engines/current_liabilities.py` | Current liabilities snapshot (BPP 2.01): `current_liabilities_at()`, `current_liabilities_periods()` |
| `skills/cvm/calculations/engines/da.py` | D&A TTM (DFC description search): `da_at()`, `da_periods()` |
| `skills/cvm/calculations/engines/capex.py` | CapEx TTM (DFC description search): `capex_at()`, `capex_periods()` |
| `skills/cvm/calculations/engines/operating_cf.py` | TTM operating cash flow (DFC 6.01): `operating_cf_at()`, `operating_cf_periods()` |
| `skills/cvm/calculations/engines/investing_cf.py` | TTM investing cash flow (DFC 6.02): `investing_cf_at()`, `investing_cf_periods()` |
| `skills/cvm/calculations/engines/financing_cf.py` | TTM financing cash flow (DFC 6.03): `financing_cf_at()`, `financing_cf_periods()` |
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

---

## 🧱 Engine vs Metric — The Core Pattern

Engines are leaves (one per raw quantity, fetch from data sources). Metrics compose engines (one per ratio). Both self-register. See historical ARCHITECTURE.md for the full pattern documentation — it's the same.

### Engine inventory by category (21 engines, 6 categories):

| Category | Engines |
|----------|---------|
| market | price, dividends |
| shares | shares |
| dre | earnings, revenue, gross_profit, ebit, ebt, tax |
| bpa | current_assets, cash, total_assets |
| bpp | pl, debt, current_liabilities |
| dfc | da, capex, operating_cf, investing_cf, financing_cf |

### Metric inventory by type (22 metrics):

| Type | Metrics |
|------|---------|
| Per-share + price ratio | lpa (LPA+P/L), vpa (VPA+P/VPA), dpa (DPA+DY+Payout), rps (RPS+PSR), ev_ebitda (EBITDA/share+EV/EBITDA), p_ebit (EBIT/share+P/EBIT), p_fco (FCO/share+P/FCO), p_fcf (FCF/share+P/FCF) |
| Fundamental ratio | roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin, debt_equity, net_debt_ebitda, asset_turnover, capex_revenue, current_ratio, graham_number, effective_tax_rate |

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
│   ├── ... (17 more engines)
│
└── metrics/  (compose engines)
    ├── lpa.py → price + earnings + shares
    ├── roe.py → earnings + pl
    ├── ev_ebitda.py → price + shares + debt + cash + ebit + da
    ├── roic.py → ebit + tax + ebt + pl + debt + cash (v2.0 EBT-based NOPAT)
    ├── effective_tax_rate.py → tax + ebt
    └── ... (17 more metrics)

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

## 📐 Key Design Patterns

1. **Central `_registry.py`** — single source of truth for auto-discovery
2. **Engine categories** — `list_engines(category="dre")` for filtering
3. **TTM derivation** — DFP_prior - ITR_prior_same + ITR_current (flow engines)
4. **Snapshot lookup** — most recent BPP/BPA snapshot <= date (balance engines)
5. **Description-based search** — da + capex search DFC by descricao keywords
6. **Multi-code sum** — debt sums BPP 2.01.04 + 2.02.01
7. **Step-function optimization** — precompute periods, O(1) lookups per day
8. **Flexible MetricSpec** — per_share fields optional for fundamental ratios
9. **PT + EN aliases** on all metrics
10. **Idempotent auto-discovery** — `_done` flag prevents re-registration

---

*Last updated: 2026-07-28 (v1.2). See [API.md](API.md) for function signatures, [ROADMAP.md](ROADMAP.md) for deferred items, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
