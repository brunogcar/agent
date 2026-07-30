<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v2.0** | 2026-07-30 | **skills/_base.py extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base.py` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base.py) instead of 11. Historical's `_auto_register_metric_history_modes()` (which auto-registers `<metric>_history` modes from calculations METRICS) was PRESERVED — see [ARCHITECTURE.md](ARCHITECTURE.md). |
| **v1.2** | 2026-07-29 | **Modular split + dashboard mode.** Split monolithic `historical.py` (253 lines) into `_registry.py` + `modes/` (3 explicit mode files: `ratio_history`, `summary`, `dashboard`) + `helpers.py` + `report.py` — mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends`/`governance` modular pattern (`_registry.py` + `modes/*.py` auto-discovered via `@register_mode`). New `dashboard` mode produces a multi-tab dashboard payload for the report tool. New `historical_dashboard` adapter (report tool v1.7, 71st adapter). Historical now exposes 40 modes total (37 auto-generated `<metric>_history` + 3 explicit: `ratio_history`, `summary`, `dashboard`). The metric/engine library still lives in `calculations/` (unchanged from v2.2). |
| **v2.2** | 2026-07-26 | **Phase 1 refactor: extract calculations.** Engines (16) + metrics (17) + registry moved to shared `skills/cvm/calculations/`. Historical now imports from calculations. Test files split by metric name and moved to `tests/skills/cvm/calculations/`. Historical retains only `historical.py` + `__init__.py` + `test_historical.py`. 355 tests pass. |
| **v2.1** | 2026-07-26 | **Tier 4+5+6: 7 new metrics + 3 new engines.** Tier 4 (0 new engines): net_margin (Margem Líquida), ebitda_margin (Margem EBITDA), debt_equity (Dívida/PL), net_debt_ebitda (DL/EBITDA), asset_turnover (Giro de Ativos). Tier 5 (1 new engine): capex engine (DFC description search for imobilizado/intangivel, TTM, category=dfc) + capex_revenue metric (CapEx/Receita). Tier 6 (2 new engines): total_assets engine (BPA codigo 1, actual Ativo Total — existing assets.py uses 1.01 which is Ativo Circulante), current_liabilities engine (BPP 2.01, Passivo Circulante) + current_ratio metric (Liquidez Corrente). All 7 new metrics are fundamental ratios (per_share=None). PT aliases on all. 355 tests. Now 16 engines + 17 metrics. |
| **v1.9** | 2026-07-26 | **EV/EBITDA + cash engine + da engine + ROIC cash update.** 2 new engines: `cash.py` (BPA 1.01.01 Caixa e Equivalentes, snapshot, category=bpa), `da.py` (D&A from DFC -- first description-based search engine, TTM, category=dfc, NEW category). New `metrics/ev_ebitda.py` (EV/EBITDA -- composes 6 engines: price+shares+debt+cash+ebit+da, the most complex metric). Per-share value: EBITDA/Ação = (EBIT+D&A)/shares. Ratio: EV/EBITDA = (price×shares+debt-cash)/(EBIT+D&A). Updated ROIC to subtract cash from invested capital (IC = PL+Debt-Cash). 319 tests. Now 13 engines + 10 metrics + 6 categories. |
| **v1.8** | 2026-07-26 | **ROIC (Return on Invested Capital).** 2 new engines: `tax.py` (DRE 3.08 IR+CSLL TTM, category=dre), `debt.py` (BPP 2.01.04+2.02.01 Empréstimos e Financiamentos snapshot, category=bpp, sums 2 codes). New `metrics/roic.py` (ROIC = NOPAT / Invested Capital -- first metric to compose 4 engines: ebit + tax + pl + debt). NOPAT = EBIT - max(0, tax_expense). Invested Capital = PL + Debt (simplified -- no cash subtraction yet, cash engine comes in EV/EBITDA). PT aliases: retorno_capital_investido. 294 tests. Now 11 engines + 9 metrics. |
| **v1.7** | 2026-07-26 | **ROA + Gross Margin + Operating Margin.** 3 new engines: `assets.py` (BPA 1.01 Ativo Total snapshot, category=bpa), `gross_profit.py` (DRE 3.03 Lucro Bruto TTM, category=dre), `ebit.py` (DRE 3.05 EBIT TTM, category=dre). 3 new fundamental ratio metrics: `roa.py` (ROA = earnings / assets), `gross_margin.py` (Margem Bruta = gross_profit / revenue), `operating_margin.py` (Margem Operacional = EBIT / revenue). All 3 follow the ROE pattern (per_share=None, single-dataset chart). All auto-generated via the registry — zero edits to __init__.py, historical.py, or adapters. PT aliases: retorno_ativos (roa), margem_bruta/gm (gross_margin), margem_operacional/om (operating_margin). 272 tests. Now 9 engines + 8 metrics. |
| **v1.6** | 2026-07-26 | **Engine categories + Portuguese aliases.** Added `category` field to EngineSpec (market, shares, dre, bpa, bpp, dfc, other) for organizational grouping. New `list_engines(category=...)` filter + `list_engine_categories()` helper. All 6 engines tagged: price/dividends=market, shares=shares, earnings/revenue=dre, pl=bpp. Added Portuguese aliases to all 5 metrics: preco_lucro (lpa), preco_vpa/p_vpa (vpa), rendimento/rendimento_dividendo/div_yield (dpa), preco_venda/p_venda (rps), retorno_pl/retorno_patrimonio (roe). Decision: use category field instead of subfolders — revisit subfolders at 15+ engines. 245 tests. |
| **v1.5** | 2026-07-26 | **ROE metric + fundamental ratio support.** Extended `MetricSpec` to support fundamental ratios (per_share fields now optional — `None` for metrics like ROE that don't produce a per-share value). New `metrics/roe.py` (ROE = TTM earnings / PL — first fundamental ratio, no price or shares needed). Chart adapter factory handles `per_share_key=None` (single-dataset chart instead of dual). Summary adapter handles `per_share_key=None` (skips per-share KPI/row). `_metric_history()` handles `per_share_key=None`. Updated docs to clarify metrics include 3 types: per-share values, price ratios, fundamental ratios. 233 tests. Now 6 engines + 5 metrics. |
| **v1.4.1** | 2026-07-26 | **Remove manual inventory from `__init__.py` docstrings.** The `engines/__init__.py` and `metrics/__init__.py` had a manual inventory list that required editing every time a new engine/metric was added — defeating the purpose of auto-discovery. Removed the inventory list. The registry (`list_engines()` / `list_metrics()`) is now the sole source of truth. Added NEVER DO rule #13: never edit `__init__.py` for inventory. Now adding an engine/metric = drop a file + `register_*()`, zero edits to `__init__.py`. |
| **v1.4** | 2026-07-26 | **Revenue engine + RPS/PSR metric.** New `engines/revenue.py` (TTM net revenue from DFP+ITR DRE 3.01 — mirrors earnings.py with codigo 3.01 instead of 3.11). New `metrics/rps.py` (RPS per-share + PSR ratio — mirrors lpa.py with revenue engine instead of earnings). `rps_history` mode auto-generated. `historical_rps_chart` adapter auto-registered (dual-axis: RPS left, PSR right). Aliases: psr, p/sr, price_sales → rps. 212 tests. Now 6 engines + 4 metrics. |
| **v1.3.1** | 2026-07-26 | **Dividends date fallback + dual-axis charts.** Fixed `dividends_at()` to use `COALESCE(payment_date, last_date_prior, approved_on)` as the event date — `paymentDate` is often NULL for older B3 dividends, causing DPA=None for historical dates. Renamed `_get_all_payment_dates` → `_get_all_event_dates`. Added dual-axis chart support: adapters emit `yAxisID` per dataset (per-share → "y" left, ratio → "y1" right); `charts.py` auto-detects `yAxisID` and adds `scales` config with two Y axes. DPA chart now readable (DPA ~4.5 on left, Div Yield ~0.10 on right). Updated dpa_history to include `lpa` in series entries. 175 tests. |
| **v1.3** | 2026-07-26 | **Central registry + engine self-registration + DPA metric.** Moved `_registry.py` from `metrics/_registry.py` to the skill top level (`skills/cvm/historical/_registry.py`). It now handles BOTH engines and metrics auto-discovery (globs `engines/*.py` AND `metrics/*.py`). New `EngineSpec` dataclass + `register_engine()` — engines self-register like metrics. New `engines/dividends.py` (DPA TTM from B3 cash_dividends). New `metrics/dpa.py` (DPA + Div Yield + Payout — first metric with a bonus ratio + first to compose 4 engines). `engines/__init__.py` + `metrics/__init__.py` simplified to minimal docstrings. 170 tests. This skill is now the pattern template for central auto-discovery + registry architecture. |
| v1.2 | 2026-07-26 | **Auto-discovery + registry + per-share-and-ratio pattern.** New `metrics/_registry.py` with `MetricSpec` dataclass + `register_metric()` + `resolve_metric()`. Auto-discovery for both `engines/` and `metrics/` via glob + importlib. `<metric>_history` modes auto-generate from the registry. Chart adapters auto-register. Renamed `pe.py` → `lpa.py` (metric file = per-share quantity name). Each metric now produces BOTH a per-share value (LPA, VPA) AND a price ratio (P/L, P/VPA). Dual-dataset charts. Metric-aware summary with both per-share + ratio + engine components. Alias resolution: pe/pl/p/l → lpa, pvpa/p/vpa → vpa. 130 tests. |
| v1.1 | 2026-07-26 | PL engine + VPA metric + engine/metric separation. New `engines/pl.py` (Patrimônio Líquido snapshot from DFP+ITR BPP 2.03). New `metrics/vpa.py` (P/VPA = price / (PL / shares)). New `vpa_history` mode. `summary` + `ratio_history` made metric-aware. Documented engine vs metric pattern. |
| v1.0 | 2026-07-25 | Initial implementation. 3 modes: pe_history, ratio_history, summary. TTM earnings engine (DFP + ITR derivation). Price engine (COTAHIST). Shares engine (FRE + investsite fallback). P/L metric. 2 report adapters. |

---

### ⚠️ Breaking Changes

#### v1.5 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `MetricSpec` per_share fields now optional | `per_share_label`, `per_share_key`, `per_share_fn` default to `None`. | No migration — existing metrics still pass all three. Fundamental metrics (ROE) pass `None`. |
| Chart adapter produces 1 dataset for fundamental metrics | Was: always 2 datasets. Now: 2 for per-share+ratio metrics, 1 for fundamental-only. | Chart builder handles both. No migration. |

#### v1.3 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/_registry.py` moved → `_registry.py` (top level) | Old import path no longer exists. | `from skills.cvm.calculations.metrics._registry import ...` → `from skills.cvm.calculations._registry import ...` |
| `list_all_names()` renamed → `list_all_metric_names()` | Function renamed for clarity. | Update imports. |
| `engines/__init__.py` no longer does auto-discovery | Auto-discovery moved to central `_registry.py`. | No migration — engines still work. |
| `metrics/__init__.py` no longer does auto-discovery | Auto-discovery moved to central `_registry.py`. | No migration — metrics still work. |

#### v1.2 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/pe.py` renamed → `metrics/lpa.py` | Old import path no longer exists. | `from skills.cvm.calculations.metrics.pe import ...` → `from skills.cvm.calculations.metrics.lpa import ...` |
| `pe_history` mode removed | Old mode name no longer in MANIFEST. | Use `lpa_history` instead. |
| `vpa` key in series changes meaning | Was: P/VPA ratio. Now: VPA per-share value. | The ratio is now under the `pvpa` key. Update chart/table consumers. |
| `METRICS` dict format changes | Was: `dict[str, str]` (name → description). Now: `dict[str, MetricSpec]`. | Use `METRICS["lpa"].ratio_label` instead of `METRICS["lpa"]`. |
| `summary()` result: `current` block changes | Now includes both per-share value and ratio. | Check `result["metric"]` to know which keys are present. |
| `historical_pe_chart` adapter renamed | Was: `historical_pe_chart`. Now: `historical_lpa_chart`. | Update `config["adapter"]` calls. |
| Chart adapters now produce 2 datasets | Was: 1 dataset (ratio only). Now: 2 datasets (per-share + ratio). | Chart builder handles multi-dataset natively. |

#### v1.1 — 2026-07-26

| Change | Impact | Migration |
|--------|--------|-----------|
| `metrics/pvpa.py` renamed → `metrics/vpa.py` | Old import path no longer exists. | `from skills.cvm.calculations.metrics.pvpa import ...` → `from skills.cvm.calculations.metrics.vpa import ...` |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | ~~EV/EBITDA metric~~ | ~~Done in v1.9~~ | ✅ |
| 2 | ~~ROIC metric~~ | ~~Done in v1.8~~ | ✅ |
| 3 | **ROIC metric** (roic) | Return on Invested Capital = NOPAT / invested capital. Needs NOPAT (earnings + tax) + invested capital (PL + debt). Fundamental ratio. | P2 |
| 4 | **Backtest skill** | Reuse historical engines + metrics. `skills/cvm/backtest/`. Signal generation + return computation. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Intraday data | COTAHIST is daily. Intraday needs B3 API trades. | Skip |
| 2 | International stocks | CVM/B3 data only. US stocks need a different data source. | Skip |
| 3 | Options pricing | COTAHIST has options data (BDI filter excludes it). Would need separate handling. | Skip |
| 4 | Standalone quarter computation | ITR is cumulative. Standalone T2/T3/T4 derivation belongs in the financials skill. | Skip |
| 5 | Shared registry helper across skills | Each skill copies the pattern (no cross-skill coupling). The pattern is small enough (~50 lines). | Skip |
| 6 | Rename `metrics/` → `ratios/` | "Metric" is a superset of "ratio" — covers per-share values, price ratios, AND fundamental ratios. Renaming would make `per_share_label` field name confusing. High-risk (20+ files) for zero functional benefit. Revisit if confusing after ROA/ROIC. | Skip |

---

## 📐 Pattern Template Notes

This skill is the **pattern template** for central auto-discovery + registry architecture. Other skills that need extensibility (e.g., a future screener with multiple filter metrics) should copy:

1. **Central `_registry.py` at the skill top level** — handles auto-discovery for both `engines/` and `metrics/` subfolders. Single source of truth.
2. **Engine/metric separation** — engines are leaves (one per raw quantity), metrics compose engines.
3. **Self-registration (BOTH layers)** — engines call `register_engine(EngineSpec(...))`, metrics call `register_metric(MetricSpec(...))`. Consistent pattern.
4. **Spec dataclasses** — `EngineSpec` + `MetricSpec` hold all metadata (name, functions, labels, aliases, source).
5. **Alias resolution** — `resolve_metric()` accepts canonical names + aliases.
6. **Auto-generated MANIFEST modes** — `<metric>_history` modes appear in the MANIFEST automatically.
7. **Auto-registered adapters** — chart/table adapters auto-register from the registry.
8. **Idempotent auto-discovery** — `_auto_discover()` uses a `_done` flag to avoid re-running on re-import.
9. **Flexible MetricSpec** — per_share fields optional (None for fundamental ratios like ROE). Chart/summary adapters handle both per-share+ratio metrics AND fundamental-only metrics.
10. **Dual-axis charts via yAxisID** — per-share value on left axis, price ratio on right axis. Fundamental metrics get single-axis (one dataset).

**Do NOT create a shared registry helper across skills.** Each skill has its own `_registry.py`. Skills should be independent — the pattern is small enough that copying is fine, and a shared helper would couple skills that should evolve independently.

---

*Last updated: 2026-07-30 (v2.0).*
