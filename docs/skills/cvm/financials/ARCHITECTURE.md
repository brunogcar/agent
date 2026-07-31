<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|------|---------|
| `skills/_base.py` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |

```text
skills/cvm/financials/
├── __init__.py        [v2.0] uses auto_discover_modes() + make_route() from skills/_base.py — ~50 lines
├── _registry.py       [v2.0] delegates to skills/_base.py — creates skill's own MODES dict via make_registry(). ~16 lines.
├── modes/             one file per mode, auto-discovered via importlib
│   ├── __init__.py    minimal package marker
│   ├── quarterly.py   @register_mode("quarterly")   — default, 8Q
│   ├── annual.py      @register_mode("annual")      — 5Y from DFP
│   ├── complete.py    @register_mode("complete")    — by grupo + key codes
│   ├── summary.py     @register_mode("summary")     — combined latest + current_ratios
│   └── dashboard.py   @register_mode("dashboard")   — 5-tab thin composition (v1.5)
├── fetchers.py        internal data fetching from DFP/ITR (_build_* + _get_* + _extract_metrics)
├── helpers.py         _safe_call, _compute_ttm_section (shared utilities)
├── report.py          dashboard section builders (composition logic for dashboard mode)
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
├── test_dashboard.py      # TestDashboardMode (5-tab payload assertions) — added v1.5
└── test_route.py          # TestFinancialsRoute (3 tests)
```

89 tests total (v1.6 — `test_dashboard.py` added in v1.5; per-mode test imports updated to `from skills.cvm.financials.modes.<mode> import <fn>` after the v1.6 file split).

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
| `dashboard` | — | summary + report builders | 5-tab thin composition (Overview/DRE/Balanço/DFC/Ratios) for report tool's dashboard action (v1.5) |

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

---

*Last updated: 2026-07-30 (v1.8 — DRE mode + 3.07 added to SUMMARY_CODES/KEY_CODES_BY_GRUPO/_extract_metrics; see [DFP statement charts of accounts](../../data_sources/cvm/dfp/ARCHITECTURE.md) for DRE/DVA chart-of-accounts docs).*
