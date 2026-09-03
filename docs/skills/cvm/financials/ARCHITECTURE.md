<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

```text
skills/cvm/financials/
├── __init__.py        manifest + route() dispatch (auto-discovery)
├── _registry.py       ModeSpec + register_mode + MODES dict
├── modes/             one file per mode, auto-discovered via importlib
│   ├── __init__.py    minimal package marker
│   ├── quarterly.py   @register_mode("quarterly")   — default, 8Q
│   ├── annual.py      @register_mode("annual")      — 5Y from DFP
│   ├── complete.py    @register_mode("complete")    — by grupo + key codes
│   ├── summary.py     @register_mode("summary")     — combined latest + current_ratios
│   ├── dashboard.py   @register_mode("dashboard")   — 11-tab thin composition (v1.5; v1.12 reorg; v1.15 TTM+YoY; v1.16 dashboard v3; v1.17 single-fetch; v1.24 quarterly tables + period toggle; v1.25 ALL charts inside toggle)
│   ├── bpa.py         @register_mode("bpa")         — Balance Patrimonial Ativo (v1.12)
│   ├── bpp.py         @register_mode("bpp")         — Balance Patrimonial Passivo (v1.12)
│   ├── dre.py         @register_mode("dre")         — Demonstração do Resultado (v1.12)
│   ├── dfc.py         @register_mode("dfc")         — Demonstração dos Fluxos de Caixa (v1.12)
│   ├── dva.py         @register_mode("dva")         — Demonstração do Valor Adicionado (v1.12)
│   └── _statement_sections.py  shared section classifiers + reshape helper (v1.12)
├── fetchers.py        internal data fetching from DFP/ITR (_build_* + _get_* + _extract_metrics + _fetch_all_statements_annual [v1.17] + _fetch_all_statements_quarterly [v1.24])
├── helpers.py         _safe_call, _compute_ttm_section (shared utilities)
├── report/            dashboard section builders — PACKAGE since v2.0 (was monolithic report.py: 3981 lines, 47 functions; split for parity with valuation v2.0)
│   ├── __init__.py    thin re-exports — ALL 34 public builders + 18 private helpers re-exported for backward compat (`from skills.cvm.financials.report import X` still works)
│   ├── _helpers.py    shared primitives: _fmt, _num_or_none, _pct_of, _period_sort_key, _format_period_label; constants (_METRIC_LABELS, _RATIO_PCT_KEYS, _INDICADORES_CATEGORIES, _VALUATION_CHART_*, _GROUP_CHART_COLORS)
│   ├── overview.py    Overview tab: build_overview_kpis, build_overview_sections (Quarterly Trend with Δ% columns [v2.3] + delta-direction fix [v2.4]), build_overview_trend_chart (Trajetória Anual — bar + unified colors + green price line [v2.4 revamp]), build_financials_radar [v1.22], build_financials_heatmap [v1.22] (tooltips [v2.3]), build_quality_of_earnings_section + build_quality_of_earnings_chart [v2.4 F16], _fetch_year_end_prices, _attach_price_overlay [v1.23]
│   ├── indicadores.py Indicadores tab: build_indicadores_section + category/grouping helpers (sub-tabs split in v1.19; valuation sub-tab split into 3 charts in v1.25)
│   ├── crescimento.py Crescimento tab: build_crescimento_sections (relocated from Indicadores in v1.25)
│   ├── statements.py  shared statement builders: build_multi_period_table [v1.23], _statement_table_section, _merge_bpa_bpp_periods, _build_period_toggle_sections [v1.24 — annual+quarterly wrapper]
│   ├── balanco.py     Balanço tab: build_balanco_section (subtab_charts_annual + subtab_charts_quarterly params [v1.25]), build_balanco_chart (6 stacked-bar charts: absolute + percentage for Completo/BPA/BPP [v1.22 rewrite]), build_balanco_decomp_charts
│   ├── dre.py         DRE tab: build_dre_sections (margins + absolute + trend charts — all inside period_toggle since v1.25), build_statement_trend_chart [v1.23 — price overlay], _build_dre_margins_chart, _build_dre_abs_chart
│   ├── dfc.py         DFC tab: build_dfc_sections (stacked + FCOvsLL + trend — all inside period_toggle since v1.25), build_dfc_trend_chart [v1.23], build_dfc_quality_section (Cash Conversion + FCF_true [v1.20]), _build_dfc_stacked_chart, _build_dfc_fco_vs_ll_chart (fco_series unpacking bug fixed in v2.0)
│   ├── dva.py         DVA tab: build_dva_sections (point-in-time doughnut + generation + sustainability stay OUTSIDE the toggle), build_dva_trend_chart [v1.23], build_dividend_sustainability_section [v1.20], _build_dva_generation_chart [v1.20]
│   ├── analysis.py    analytical sections: build_red_flags_section [v1.20] (collapsible with nested sections [v2.4 — macro now renders them]), build_dupont_section [v1.21], build_altman_z_section [v1.21], build_wacc_section [v1.21]
│   ├── periods.py     period series: build_ttm_chart, build_ttm_table, build_yoy_chart, build_yoy_table, build_period_table, build_period_chart (TTM 20 periods since v1.25, was 8)
│   ├── comprehensive.py [v2.3] comprehensive period table + indicator charts: build_comprehensive_period_table (9 sub-tables: Balanço/DRE/DFC/Crescimento/CAGR/Margens/Liquidez/Disponibilidades/EBIT-EBITDA-CAPEX), build_indicator_charts (3 bar charts: Liquidez/Disponibilidades/EBIT-EBITDA-CAPEX). [v2.4] capex_map kwarg uses real capex_at engine with FCI fallback.
│   └── error.py       error utilities + small helpers: build_error_section, _safe_engine_call, annual_metric, annual_ratio, _metrics_from_period
└── metrics.py         ratio computation (SUMMARY_CODES, KEY_CODES_BY_GRUPO, compute_ratios,
                       compute_ebitda, compute_ttm, compute_ebitda_from_engines,
                       compute_ttm_with_engines) — UNCHANGED across v1.6 split + v2.0 report split
```

**v2.0 split (2026-08-13):** the monolithic `report.py` (3981 lines, 47 functions) was split into the `report/` package above — 13 files, one per concern. `report/__init__.py` re-exports all 34 public builders + 18 private helpers so existing imports (`from skills.cvm.financials.report import build_overview_kpis` etc.) continue to work — `modes/dashboard.py` was untouched. Same pattern as `skills/cvm/calculations/engines/<stmt>/` subfolders + `skills/cvm/_shared_report/`. The only logic change in v2.0: fixed the pre-existing `fco_series, ni_series = [], [], []` unpacking bug (3-element tuple unpacked into 2 vars → `ValueError`) in `_build_dfc_fco_vs_ll_chart` (introduced in v1.25 v4 when the chart was moved from `build_dfc_quality_section`).

**v1.6 split (2026-07-29):** the 967-line `financials.py` was split into the structure above. `__init__.py` now auto-discovers modes by globbing `modes/*.py` (sorted) + `importlib.import_module()` — same pattern as `tools/git_ops/actions/` + `skills/cvm/calculations/_registry.py`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`, no edits to `__init__.py` or `_registry.py`. Public API unchanged.

**v2.0 report split (2026-08-13):** see file map above — `report.py` was split into a 13-file `report/` package. Same pattern as `skills/cvm/calculations/engines/<stmt>/` + `skills/cvm/_shared_report/`. All public symbols re-exported from `report/__init__.py` — zero downstream changes (only consumer is `modes/dashboard.py`).

### Test module tree

```text
tests/skills/cvm/financials/
├── conftest.py            # financials_env fixture — synthetic DFP + ITR DBs
├── test_metrics.py        # TestMetrics + TestTTM + TestDFCMDFallback (16 tests)
├── test_annual.py         # TestAnnualMode (3 tests)
├── test_quarterly.py      # TestQuarterlyMode + TestQuarterlyV101Regressions (5 tests)
├── test_complete.py       # TestCompleteMode (5 tests)
├── test_summary.py        # TestSummaryMode + TestSummaryV101Regressions + TestSummaryCurrentRatios (5 tests)
├── test_dashboard.py      # TestDashboardMode (7-tab payload assertions) — added v1.5; v1.12 reorg
└── test_route.py          # TestFinancialsRoute (4 tests)
```

90 tests total (v1.12 — 5 new standalone modes (bpa/bpp/dre/dfc/dva) auto-discovered; `test_dashboard.py` updated for 7-tab assertions; `test_route.py` updated for 7-tab name list).

## Data Flow

```
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')
  │
  ▼  quarterly mode
  │  1. resolve_company("PETR4") → empresa_ids (via bridge, auto-sync)
  │  2. Fetch ITR cumulative (meses=3/6/9) for last N quarters
  │  3. Fetch DFP annual (meses=12) for Q4 derivation
  │  4. Derive standalone quarters (flows: subtract; snapshots: direct)
  │  5. Compute EBITDA = EBIT + D&A
  │  6. Compute ratios (margins, ROA/ROE annualized, debt, payout)
  │
  ▼  annual mode
  │  1. resolve_company → empresa_ids
  │  2. Fetch DFP annual (meses=12) for last N years
  │  3. Compute EBITDA + ratios
  │
  ▼  dashboard mode (v1.24+ quarterly fetch)
  │  1. resolve_company("PETR4") → empresa_ids
  │  2. _fetch_all_statements_annual() — ONE SQL query for ALL 5 statements × KEY_CODES (v1.17)
  │  3. _fetch_all_statements_quarterly() — ITR+DFP for ALL KEY_CODES (v1.24):
  │     • BPA/BPP: snapshot — ITR stores meses=12 (annual), carried forward for Q1-Q3 (see INSTRUCTIONS v1.25)
  │     • DRE/DFC/DVA: flow — standalone derivation from cumulative (meses=3/6/9/12)
  │     • Up to 20 quarterly periods
  │  4. Pre-render BOTH annual + quarterly tables, wrap in _build_period_toggle_sections() (v1.24)
  │  5. ALL time-series charts pre-rendered for both periods, also wrapped in period_toggle (v1.25):
  │     • DRE: margins + absolute + trend
  │     • DFC: stacked + FCOvsLL + trend
  │     • Balanço: 6 stacked-bar charts (Completo/BPA/BPP × abs/pct)
  │     • Point-in-time charts (DVA doughnut, generation, DFC quality, DVA sustainability) stay OUTSIDE
  │  6. Frontend: togglePeriod JS swaps visibility + calls chart.resize() on the now-visible panel (v1.25)
```

## Standalone Quarter Derivation

ITR stores cumulative values (Q1=3meses, Q2=6, Q3=9). Standalone derivation:

| Quarter | Flow items (DRE/DFC/DVA) | Snapshot items (BPA/BPP) |
|---------|--------------------------|--------------------------|
| Q1 | cum3 (ITR) | period-end value (ITR meses=3) |
| Q2 | cum6 − cum3 | period-end value (ITR meses=6) |
| Q3 | cum9 − cum6 | period-end value (ITR meses=9) |
| Q4 | DFP annual (meses=12) − cum9 | period-end value (DFP meses=12) |

Snapshots are point-in-time balances — no subtraction needed. Flows are cumulative within the year — subtraction gives the standalone period.

## EBITDA Formula

```
EBITDA = EBIT (DRE 3.05) + Depreciation & Amortization (DFC 6.01.01.02)
```

D&A comes from the **cash flow statement** (DFC), not the DRE. If D&A is missing, EBITDA = EBIT.

## Key Account Codes

Summary metrics use these CVM account codes:

| Metric | Code | Grupo | Type |
|--------|------|-------|------|
| Ativo Total | 1 | BPA | snapshot |
| Caixa | 1.01.01 | BPA | snapshot |
| Passivo Total | 2 | BPP | snapshot |
| Patrimônio Líquido | 2.03 | BPP | snapshot |
| Dívida Bruta (Circulante) | 2.01.04 | BPP | snapshot |
| Dívida Bruta (Não Circulante) | 2.02.01 | BPP | snapshot |
| Receita Líquida | 3.01 | DRE | flow |
| Lucro Bruto | 3.03 | DRE | flow |
| EBIT | 3.05 | DRE | flow |
| Resultado Financeiro | 3.06 | DRE | flow |
| Lucro Líquido | 3.11 | DRE | flow |
| FCO | 6.01 | DFC_MI | flow |
| FCI | 6.02 | DFC_MI | flow |
| FCF | 6.03 | DFC_MI | flow |
| D&A (for EBITDA) | 6.01.01.02 | DFC_MI | flow |
| Proventos | 7.08.04 | DVA | flow |

## Ratio Formulas

| Ratio | Formula | Notes |
|-------|---------|-------|
| Marg. Bruta | Lucro Bruto / Receita | |
| Marg. EBITDA | EBITDA / Receita | |
| Marg. EBIT | EBIT / Receita | |
| Marg. Líquida | Lucro Líquido / Receita | |
| ROA | (Lucro Líquido × annualize) / Ativo Total | annualize=4 for quarterly |
| ROE | (Lucro Líquido × annualize) / PL | annualize=4 for quarterly |
| Dívida Bruta/PL | Dívida Bruta / PL | |
| Dívida Líquida | Dívida Bruta − Caixa | |
| Payout | Proventos / Lucro Líquido | |

**Note:** Quarterly ROA/ROE are annualized (×4). TTM-based ratios (trailing twelve months) are on the roadmap.

## Modes

| Mode | Default periods | Source | Returns |
|------|----------------|--------|---------|
| `quarterly` | 8 | ITR + DFP | standalone quarters + ratios |
| `annual` | 5 | DFP | annual metrics + ratios |
| `complete` | 8 (quarterly) / 5 (annual) | ITR + DFP or DFP | full statements by grupo + key codes |
| `summary` | 1 annual + 4 quarterly | all + calculations | combined latest + trend + `current_ratios` |
| `dashboard` | — | annual + quarterly + calculations + 5 standalone statement modes | 7-tab thin composition (Overview / Indicadores / Crescimento / Balanço / DRE / DFC / DVA) for report tool's dashboard action (v1.5; v1.12 reorg) |
| `bpa` | 1 (annual) | DFP (BPA grupo) | asset accounts (dict-keyed with section labels) (v1.12) |
| `bpp` | 1 (annual) | DFP (BPP grupo) | liabilities + equity accounts (dict-keyed) (v1.12) |
| `dre` | 1 (annual) | DFP (DRE grupo) | income-statement accounts (dict-keyed) (v1.12) |
| `dfc` | 1 (annual) | DFP (DFC_MI grupo) | cash-flow accounts (dict-keyed) (v1.12) |
| `dva` | 1 (annual) | DFP (DVA grupo) | value-added accounts (dict-keyed with Geração/Distribuição sections) (v1.12) |

---

## Calculations Integration (v1.3)

`summary()` mode delegates point-in-time ratios to `skills.cvm.calculations.metrics.*`:

| Metric | Calculations function | Engines composed | Needs price? |
|--------|----------------------|------------------|--------------|
| ROIC | `roic_at` | ebit + tax + pl + debt + cash | No |
| Graham Number | `graham_number_at` | earnings + pl + shares | No (returns BRL target) |
| EV/EBITDA | `ev_ebitda_at` | price + shares + debt + cash + ebit + da | Yes (cotahist) |
| P/FCF | `p_fcf_at` | price + shares + operating_cf + investing_cf | Yes (cotahist) |
| P/EBIT | `p_ebit_at` | price + shares + ebit | Yes (cotahist) |
| P/FCO | `p_fco_at` | price + shares + operating_cf | Yes (cotahist) |

### Why per-period modes (quarterly / annual / complete) do NOT use calculations metrics

Calculations engines are point-in-time: `*_at(company, date)` returns a single TTM/snapshot value for a given date. Financials' statement-rendering modes need **per-period ratios** (e.g., ROE for each of 8 quarters), and they already have the raw `{codigo: valor}` dicts in memory after fetching the statements. Calling calculations metrics per period would re-query DFP/ITR (via `connect_dfp`/`connect_itr`) for each period — wasteful and slower than computing from the already-fetched dict.

The two patterns coexist intentionally:
- **`compute_ratios(metrics, is_quarterly)`** in `metrics.py` — operates on raw dicts, used by `quarterly` + `annual` modes for per-period ratios.
- **`<metric>_at(company, date)`** in `calculations/metrics/*` — point-in-time, used by `summary()` for current snapshot.

### Lazy import + `_safe_call` pattern

Calculations imports in `modes/summary.py` are lazy (inside `summary()` function body, not at module top) so importing the modes module does NOT trigger calculations registry initialization (and the corresponding `PLANNER_MODEL` env-var requirement). Each metric is wrapped in `_safe_call(fn, company, today)` which catches `FileNotFoundError` (missing `cotahist.db`, `fre.db`) and any other exception, returning `None`. This makes the integration best-effort: a missing DB degrades gracefully instead of crashing the whole `summary()` call. *(v1.6: this pattern moved verbatim from the deleted `financials.py` to `modes/summary.py`.)*

[v1.4] In `metrics.py`, by contrast, the engine-backed variants' imports (`ebit_at`, `da_at`, `revenue_at`, `ttm_earnings_at`, `operating_cf_at`, `investing_cf_at`, `financing_cf_at`) were moved to module top-level in a `[v1.4-financials-migration]` block. This is intentional: `metrics.py` is imported lazily by the per-period modes (`modes/quarterly.py`, `modes/annual.py`, `modes/complete.py`) only when needed, and at that point `PLANNER_MODEL` is already set (financials' conftest sets it at import time). Moving the imports to module top makes the dependency explicit + mockable as `skills.cvm.financials.metrics.<fn>_at` (which is how `test_metrics.py` patches them). Engine calls inside the variants are still wrapped in `_safe_engine_call` (returns None on any error) so a missing DB degrades gracefully.

## Dashboard Architecture

The `dashboard` mode is a thin composition mode — it calls `annual()`, `quarterly()`, `compute_all_ratios()`, and 5 standalone statement modes (bpa/bpp/dre/dfc/dva) in parallel via `ThreadPoolExecutor` (8 workers sharing one `engine_cache_scope`). Each statement-mode call is wrapped in `_safe_call()` — a failure degrades the corresponding tab to an error text section.

### 11-Tab Structure (4 sidebar groups)

| Group | Tabs |
|-------|------|
| **Resumo** | Overview, Indicadores, Crescimento |
| **Demonstrações** | Balanço, DRE, DFC, DVA |
| **Períodos** | Anual, Trimestral QoQ |
| **Séries Temporais** | Anualizado (TTM), Trimestral YoY |

### Overview Tab — 4 Subtabs

| Subtab | Contents |
|--------|---------|
| **Cotação & Resumo** | Company info card + price chart (range selector) + summary text + 2 two_column blocks (Resultado/Margens, Balanço/Fluxo) + Quarterly Trend table (Δ% columns) |
| **Trajetória Anual** | Annual trend chart (Receita/EBITDA/Lucro bars + green price line overlay) |
| **Análise de Risco** | WACC table (COE/Kd/weights/tax decomposition) + DuPont 3-step ROE + Altman Z-Score (X1-X5 components) + Red Flags Contábeis (collapsible) + Qualidade do Lucro (NI vs FCO + accruals) |
| **Visão Multidimensional** | Radar (6-axis) + Heatmap (10 metrics, color-coded with tooltips) |

### Section Types

| Type | Used by | Notes |
|------|---------|-------|
| `table` | Most tabs | `data_table` macro; supports `wide` (frozen columns), `sortable`, `negative_red`, `positive_green` |
| `chart` | All tabs with charts | Chart.js; `_fixedYWidth=90` + `_absMillions` for R$ (mi) alignment |
| `ratio_grid` | Indicadores tab | Per-category grid with tooltips on metric names |
| `subtabs` | Overview, Trimestral YoY | Nested tab navigation |
| `collapsible` | Red Flags | Collapsible body renders nested `sections` via `_section_inner` |
| `period_toggle` | Balanço, DRE, DFC, DVA | Trimestral/Anual toggle (pre-render + JS swap) |
| `two_column` | Overview (Cotação & Resumo) | Side-by-side tables (Resultado/Margens, Balanço/Fluxo) |
| `heatmap` | Overview (Visão Multidimensional) | Color-coded metric table with tooltips |
| `company_info` | Overview (Cotação & Resumo) | Company header card (name, CNPJ, setor, etc.) |
| `text` | Error fallbacks | Plain text block |

### Comprehensive Period Tables (Períodos/Séries Temporais tabs)

The 4 period tabs (Anual, Trimestral QoQ, Anualizado, Trimestral YoY) each show 9 sub-tables built by `report/comprehensive.py::build_comprehensive_period_table`:

1. **Balanço Patrimonial** (11 rows) — Ativo Total, Ativo Circ, Estoques, Ativo Não Circ, Passivo Total, Passivo Circ, Fornecedores, Passivo Não Circ, PL, Part. Acionistas NC, Capital Social
2. **Demonstrativo de Resultado** (4 rows) — Receitas, Resultado Bruto, Atribuído NC, Lucro Líquido
3. **Fluxo de Caixa** (8 rows) — FCO, D&A, FCI, FCF, FCT (computed), FCL (computed), Saldo Inicial, Saldo Final (computed)
4. **Crescimento** (3 rows) — Cres. RL/RB/LL (period-over-period %)
5. **CAGR** (3 rows) — CAGR RL/RB/LL (5-period compound)
6. **Margens** (4 rows) — Bruta, EBIT, EBITDA, Líquida
7. **Liquidez e Alavancagem** (4 rows) — Giro Ativos, Liquidez Corrente, Liquidez Imediata, Div Br/Patrim
8. **Disponibilidades e Endividamento** (4 rows) — Disponibilidades, Dív. Bruta, Dív. Líquida, Capital Giro
9. **EBIT, EBITDA e CAPEX** (3 rows) — EBIT, EBITDA, CAPEX (real capex engine with FCI fallback)

Each tab also has: a trend chart (Receita/EBITDA/Lucro bars), a margins bar chart, and 3 indicator bar charts (Liquidez, Disponibilidades, EBIT/EBITDA/CAPEX). Frozen Métrica column (250px) with sticky section headers.

### Parallel Fetch (8 tasks in `engine_cache_scope`)

| Task | Fetches | Caches |
|------|---------|-------|
| `annual` | DFP annual (10 periods) via `annual()` mode | Engine cache (shared) |
| `quarterly` | ITR + DFP quarterly (20 periods) via `quarterly()` mode | Engine cache (shared) |
| `statements` | ALL 5 statements annual via `_fetch_all_statements_annual()` (1 SQL query) | Engine cache (shared) |
| `statements_q` | ALL 5 statements quarterly via `_fetch_all_statements_quarterly()` | Engine cache (shared) |
| `ttm` | TTM (20 periods) via `ttm()` mode | Engine cache (shared) |
| `yoy` | YoY quarterly (5 years) via `yoy_quarterly()` mode | Engine cache (shared) |
| `ratios` | `compute_all_ratios()` (66 metrics, point-in-time) | Engine cache (shared) |
| `capex` | `capex_periods()` (real CapEx engine: description-search imobilizado/intangivel) | Engine cache (shared) |

Context propagation: `contextvars.copy_context()` per worker (all copies share the same cache dict — true cross-task cache sharing).

### Template Rendering

- `tools/report_ops/templates/dashboard.html` — top-level tab + section rendering, chart-render script loops (top-level, period_toggle, subtab, collapsible nested)
- `tools/report_ops/templates/macros.html` — `data_table` (wide+sortable), `_section_inner` (collapsible wrapper), `subtabs`, `period_toggle`, `collapsible` (renders nested `sections`), `two_column`, `ratio_grid`, `heatmap_table`
- `tools/report_ops/templates/js/dashboard_charts.html` — `_renderChart`, `_applyFixedYWidth`, `_applyAbsMillions`, `_applyPctYAxis`, `togglePeriod`, `toggleChartCollapsible`

### Key Engine Dependencies

| Dashboard feature | Engine | Source |
|-------------------|--------|--------|
| CapEx (comprehensive table + indicator chart) | `capex_at` / `capex_periods` | `skills/cvm/calculations/engines/dfc/capex.py` |
| WACC components (COE, Kd, weights) | `wacc_history` | `skills/cvm/calculations/metrics/wacc.py` |
| Altman Z components (X1-X5) | `altman_z_history` | `skills/cvm/calculations/metrics/altman_z.py` |
| Price overlay (Trajetória Anual + DRE/DFC/DVA trend) | `price_series` | `skills/cvm/calculations/engines/price.py` |
| DFC Quality (F12) | `capex_at` + `operating_cf_at` + `ttm_earnings_at` | `skills/cvm/calculations/engines/dfc/` |
| Dividend Sustainability (F13) | `dividends_paid_at` + `ttm_earnings_at` | `skills/cvm/calculations/engines/dva/` |

---

*Last updated: 2026-09-04. See [CHANGELOG.md](CHANGELOG.md) for version history.*
