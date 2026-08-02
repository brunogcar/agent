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
│   ├── dashboard.py   @register_mode("dashboard")   — 11-tab thin composition with sidebar groups (v1.5; v1.12 reorg; v1.15 TTM+YoY; v1.16 dashboard v3)
│   ├── bpa.py         @register_mode("bpa")         — Balance Patrimonial Ativo (v1.12)
│   ├── bpp.py         @register_mode("bpp")         — Balance Patrimonial Passivo (v1.12)
│   ├── dre.py         @register_mode("dre")         — Demonstração do Resultado (v1.12)
│   ├── dfc.py         @register_mode("dfc")         — Demonstração dos Fluxos de Caixa (v1.12)
│   ├── dva.py         @register_mode("dva")         — Demonstração do Valor Adicionado (v1.12)
│   └── _statement_sections.py  shared section classifiers + reshape helper (v1.12)
├── fetchers.py        internal data fetching from DFP/ITR (_build_* + _get_* + _extract_metrics)
├── helpers.py         _safe_call, _compute_ttm_section (shared utilities)
├── report.py          dashboard section builders (composition logic for 11-tab dashboard mode — v1.16: tooltips, chart titles/descriptions, 4 new chart builders)
└── metrics.py         ratio computation (SUMMARY_CODES, KEY_CODES_BY_GRUPO, compute_ratios,
                       compute_ebitda, compute_ttm, compute_ebitda_from_engines,
                       compute_ttm_with_engines) — UNCHANGED across v1.6 split
```

**v1.6 split (2026-07-29):** the 967-line `financials.py` was split into the structure above. `__init__.py` now auto-discovers modes by globbing `modes/*.py` (sorted) + `importlib.import_module()` — same pattern as `tools/git_ops/actions/` + `skills/cvm/calculations/_registry.py`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`, no edits to `__init__.py` or `_registry.py`. Public API unchanged.

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

## Dashboard Architecture (v1.12 + v1.13 + v1.14)

**v1.12** — 7-tab dashboard (Overview / Indicadores / Crescimento / Balanço / DRE / DFC / DVA):
- `dashboard.py` is a thin composition mode — calls `annual()`, `quarterly()`, `compute_all_ratios()`, and 5 standalone statement modes (bpa/bpp/dre/dfc/dva).
- `report.py` contains section builders (`build_overview_kpis`, `build_indicadores_section`, `build_crescimento_sections`, `build_balanco_section`, `build_dre_sections`, `build_dfc_sections`, `build_dva_sections`).
- Each statement-mode call is wrapped in `_safe_call()` — a failure degrades the corresponding tab to an error text section.
- Section types: `table`, `chart`, `ratio_grid`, `subtabs`, `collapsible`, `text`.

**v1.13** — Review fixes:
- Indicadores tab split into sub-tabs by category (Valuation / Rentabilidade / Liquidez / Endividamento / Eficiência / Crescimento / Tributos).
- DVA doughnut chart shows tooltip percentages via `_tooltipPercent` flag.
- Crescimento tab uses `growth_helpers.growth_at()` with period-specific gap tolerance.

**v1.15** — TTM + YoY Quarterly modes:
- New `ttm` mode: rolling TTM (anualizado) time series — computes TTM at every historical quarter boundary via `compute_ttm_with_engines()`. Produces ~4 deseasonalized data points per year. Flow metrics (DRE/DFC) use TTM derivation; snapshot metrics (BPA/BPP) use 4-quarter averaging.
- New `yoy_quarterly` mode: same-quarter year-over-year comparison — groups quarters by Q1/Q2/Q3/Q4 and compares across years with YoY growth.
- Dashboard 7→9 tabs (added TTM tab with table + line chart, YoY Quarterly tab with table + bar chart).
- Mode families: Period views (quarterly/annual/ttm/yoy_quarterly) + Statement views (bpa/bpp/dre/dfc/dva) + Composition layers (complete/summary/dashboard).

**v1.14** — Sync guard + print output:
- `REQUIRED_SOURCES = ["dfp", "itr", "bridge"]` wired via `make_route()`.
- `route()` calls `ensure_fresh()` before dispatch — force-syncs stale sources.
- 11 `[financials]` print statements showing progress (start, fetch annual, fetch quarterly, computing ratios, 5x statement fetch, build, done).

---

*Last updated: 2026-08-01 (v1.16.1 — collective-review bugfix sprint + shared report module). See [CHANGELOG.md](CHANGELOG.md) for version history.*
