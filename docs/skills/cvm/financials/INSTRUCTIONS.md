<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill mode function** — Skills are read-only. Sync belongs in `data_sources/`. **[v1.14 exception]** The sync GUARD (`ensure_fresh()`) lives in `skills/_base.py` and is wired via `make_route(required_sources=[...])` in `__init__.py` — it triggers `data_sources/` sync functions before dispatch, but the skill mode functions themselves never call sync. This is a routing-layer concern, not a mode-function concern.
2. **Never use `float(escala)` directly** — DFP stores escala as Portuguese words ("MIL", "MILHOES"). Always use `parse_escala()` from `_db.py`.
3. **Never return cumulative values as standalone** — ITR values are cumulative. Flow items (DRE/DFC/DVA) must be subtracted to get standalone quarters. Snapshot items (BPA/BPP) use period-end value directly.
4. **Never change the EBITDA formula** — `EBITDA = EBIT (DRE 3.05) + D&A (DFC 6.01.01.02)`. The D&A comes from the cash flow statement, not the DRE.
5. **Never change the Q4 derivation** — `Q4 = DFP annual (meses=12) − ITR Q3 cumulative (meses=9)`. This requires both DFP + ITR to be synced.
6. **Never replace `compute_ratios()` with calculations metrics in `quarterly`/`annual`/`complete` modes** — Calculations engines are point-in-time (`*_at(company, date)`); per-period rendering needs ratios from raw `{codigo: valor}` dicts. The two patterns coexist intentionally. Calculations integration is confined to `summary()` `current_ratios` + `dashboard()` Indicadores tab only.
7. **Never import calculations metrics at the top of `modes/summary.py`** — Lazy-import them inside `summary()` so importing the module doesn't trigger the calculations registry (and the `PLANNER_MODEL` env-var requirement). *(v1.6: this rule was originally about `financials.py`; the file was split into `modes/summary.py` where `summary()` now lives. The same restriction applies to the new path. v1.12: `modes/dashboard.py` follows the same pattern — calculations imports are inside `dashboard()` body.)*
8. **Never call a calculations metric without `_safe_call`** — Engines may raise `FileNotFoundError` when their underlying DB (cotahist, fre, itr) is not synced. Without the wrapper, one missing DB crashes the whole `summary()` / `dashboard()`.
9. **Never create `.bak` files** — Forbidden by project rules.
10. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly. *(Exception: v1.12 was a deliberate rewrite of `dashboard.py` + `report.py` because the 5→7 tab reorg touched every section builder. Future surgical edits to these files should preserve the v1.12 structure.)*
11. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.
12. **Never duplicate SQL queries in the dashboard** — *(v1.12)* The dashboard mode must call the standalone statement modes (bpa/bpp/dre/dfc/dva) for raw account data. Each statement-mode call is wrapped in try/except so a failure in one statement degrades the corresponding tab to an error text section instead of crashing the whole dashboard.
13. **Never change the section shape produced by `report.py` builders** — *(v1.12)* Each builder returns a dict with a `type` field (`table` / `chart` / `ratio_grid` / `subtabs` / `text` / `collapsible` / `two_column`). The `financials_dashboard` adapter passes typed sections through verbatim. Changing the shape (e.g., removing the `type` field) breaks the adapter's pass-through contract.

### ALWAYS DO

1. **Always use `parse_escala()` for escala values** — `float("MIL")` crashes.
2. **Always make summary sections best-effort** — If one data source is missing, the summary should still return what's available.
3. **Always annualize ROA/ROE for quarterly** — `lucro_liquido * 4 / ativo_total`. Document that TTM is on the roadmap.
4. **Always return `period_type` in the result** — So callers know if it's "annual" or "quarterly".
5. **Always sort periods newest-first** — Consistent with other skills.
6. **Always run `compileall` before `pytest`** — Catches syntax errors early.
7. **Always split tests by mode** — `test_metrics.py` / `test_annual.py` / `test_quarterly.py` / `test_complete.py` / `test_summary.py` / `test_dashboard.py` / `test_route.py` + shared `conftest.py`. One test class per file (regression classes allowed as additional classes in the same file). *(v1.6: after the file split, per-mode test imports use `from skills.cvm.financials.modes.<mode> import <fn>` instead of `from skills.cvm.financials.financials import <fn>`.)*
8. **Always declare `REQUIRED_SOURCES` in `__init__.py`** (v1.14) — `REQUIRED_SOURCES = ["dfp", "itr", "bridge"]` + pass to `make_route(required_sources=REQUIRED_SOURCES)`. The sync guard checks freshness before each dispatch + force-syncs if stale. Tests use `CVM_SKIP_SYNC=1` (set in conftest). Per-call bypass: `route(..., skip_sync=True)`.

---

### Anti-patterns & Lessons Learned

#### v1.3 — Per-period modes can't use calculations engines
> - **What happened:** Initial Phase 3 plan considered replacing `compute_ratios()` with calculations metric calls inside `quarterly()` / `annual()` / `complete()`.
> - **Why it matters:** Calculations engines are point-in-time (`*_at(company, date)` returns ONE value for a given date). Statement-rendering modes need per-period ratios (one ratio per quarter/year, for N periods). Calling calculations per period would re-query DFP/ITR N times via `connect_dfp`/`connect_itr` — wasteful, when the dict is already in memory.
> - **Fix:** Calculations integration is confined to `summary()` `current_ratios` (a single point-in-time snapshot). Per-period modes keep their own `compute_ratios(metrics, is_quarterly)` that operates on the already-fetched `{codigo: valor}` dict. The two patterns coexist intentionally. Documented in NEVER DO #6.

#### v1.3 — Lazy import protects module load from registry initialization
> - **What happened:** Initial draft imported calculations metrics at the top of `financials.py`. Importing the module then triggered `skills.cvm.calculations._registry` auto-discovery, which transitively imports `core.config`, which requires `PLANNER_MODEL` env var. Importing financials.py for a quick smoke test would crash with `RuntimeError: PLANNER_MODEL is required`.
> - **Why it matters:** Skills should be importable without runtime env vars (tests, lint, introspection). Pulling in the calculations registry at module-load time breaks that invariant.
> - **Fix:** Lazy-import calculations metrics inside `summary()` function body. Module load no longer touches the calculations registry. Tests that don't call `summary()` stay fast (no registry init). Documented in NEVER DO #7. *(v1.6: the file split moved `summary()` to `modes/summary.py` — the lazy-import invariant now applies to that file.)*

#### v1.12 — Dashboard SQL duplication (avoided)
> - **What happened:** Initial v1.12 dashboard draft inlined `connect_dfp`/`connect_itr` calls to fetch BPA/BPP/DRE/DFC/DVA accounts directly, duplicating the SQL already in `complete()` mode's `_fetch_complete_annual`.
> - **Why it matters:** Two copies of the same SQL query would drift. When `_fetch_complete_annual` is fixed (e.g., for a new DFC_MD code), the dashboard copy would not pick up the fix.
> - **Fix:** The dashboard calls the 5 new standalone statement modes (bpa/bpp/dre/dfc/dva) — each a thin wrapper over `complete(grupo=...)` that reshapes the per-period `accounts` list into a dict-keyed shape with `section` labels. No SQL duplication. Each statement-mode call is wrapped in try/except so a failure in one statement degrades the corresponding tab to an error text section. Documented in NEVER DO #12.

#### v1.12 — Section shape contract for the adapter
> - **What happened:** Initial v1.12 dashboard sections omitted the `type` field, expecting the `financials_dashboard` adapter to infer it from the section's `name` (legacy pattern). The adapter's pass-through branch (`if sec.get("type"): return [sec]`) requires an explicit `type`.
> - **Why it matters:** Without a `type` field, the adapter falls through to the "unknown section" branch and emits a text-block "Section shape not recognized" error.
> - **Fix:** Every section produced by `report.py` builders carries a `type` field (`table` / `chart` / `ratio_grid` / `subtabs` / `text` / `collapsible` / `two_column`). The adapter passes typed sections through verbatim. The `name`-dispatched legacy branches are preserved for backward compatibility with old test data. Documented in NEVER DO #13.

#### v1.25 — Cache `import json` (happened TWICE)
> - **What happened:** The `_cache.py` module defines `_StrictJSONEncoder(json.JSONEncoder)` but the top-of-file `import json` was missing. This silently disabled the entire engine cache — every cached call fell through to the underlying function with no caching benefit, and the failure was silent (no exception, just no perf gain).
> - **Why it matters:** This bug has now happened TWICE in the project history — first in v1.10 (fixed), then AGAIN in v1.25. Each recurrence was a silent performance regression affecting every calculations engine call.
> - **Fix:** Add the missing `import json` at the top of `_cache.py`. Lesson: **ALWAYS verify imports after merging changes** — particularly when a merge involves moving/changing a module that uses a stdlib name like `json`, `datetime`, `re`. A `NameError` at module-import time would be loud, but a class inheritance reference (`json.JSONEncoder`) inside a class body that's never reached at import time is silent until someone tries to cache something. Lint with `ruff --select F401,F821` to catch unused/undefined references.

#### v1.25 — ITR BPA/BPP `meses=12` carry-forward
> - **What happened:** The quarterly statement fetcher assumed ITR BPA/BPP (balance sheet snapshots) would be stored with `meses=3/6/9` for Q1/Q2/Q3, like DRE/DFC/DVA flows. In reality, ITR stores BPA/BPP with `meses=12` (annual snapshot at the quarter-end date) — only DRE/DFC/DVA have quarterly `meses`.
> - **Why it matters:** Querying ITR with `meses IN (3,6,9)` returned NO BPA/BPP rows for Q1-Q3, so the quarterly Balanço tab appeared empty until Q4 (the DFP annual snapshot).
> - **Fix:** Query ITR with `meses IN (3,6,9,12)` for ALL grupos, and for BPA/BPP carry forward the `meses=12` snapshot value to Q1/Q2/Q3 (a balance sheet is a point-in-time snapshot — the annual value IS the Q3 value if the ITR filing date is Q3 end). DRE/DFC/DVA still derive standalone from cumulative `meses=3/6/9/12`.

#### v1.25 — CAGR key mismatch (`_cagr_at`)
> - **What happened:** `_cagr_at()` looked for keys `value`, `revenue`, `ttm`, `gross_profit` in the per-period dict, but `revenue_periods()` returns `ttm_rev` and `gross_profit_periods()` returns `ttm_gp`. CAGR for "Receita" and "Resultado Bruto" silently returned `None`.
> - **Why it matters:** The dashboard showed "—" instead of growth percentages for two of the three primary growth metrics — looked broken to users.
> - **Fix:** Always check the actual return key name of the `*_periods()` function before referencing it in `_cagr_at()`. The naming convention is `ttm_<short_metric_name>` (e.g., `ttm_rev`, `ttm_gp`, `ttm_earnings`, `ttm_ebit`). When adding a new growth metric, grep `def <metric>_periods` first to confirm the key.

#### v1.25 — Chart toggle inside `period_toggle`
> - **What happened:** Charts inside `display:none` containers (the hidden panel of a `period_toggle`) don't render — Chart.js initializes with 0×0 dimensions and stays blank even when the panel becomes visible.
> - **Why it matters:** The v1.25 task moved ALL time-series charts inside the `period_toggle` (DRE margins+abs+trend, DFC stacked+FCOvsLL+trend, Balanço 6 stacked-bar charts). Without the fix, only the visible-at-load panel's charts rendered — toggling to "Trimestral" or "Anual" showed empty chart containers.
> - **Fix:** (1) Template `_section_inner` must render chart canvases (with UNIQUE IDs — e.g., `{prefix}-pt-{i}-{period}-{j}`) for `sec.type == 'chart'` sections inside `period_toggle.annual_sections` + `period_toggle.quarterly_sections`. (2) The `_renderChart` JS must be called for every chart canvas in both panels (not just the visible one). (3) The `togglePeriod` JS must call `chart.resize()` on the now-visible panel after the visibility swap — this forces Chart.js to re-measure the canvas now that it has dimensions.

#### v2.0 — Report split pattern
> - **What happened:** `report.py` grew to 3,981 lines / 47 functions — past the point where a single-file module is navigable. Searching for a specific builder required scrolling through dozens of unrelated helpers.
> - **Why it matters:** Large monolithic files (a) slow down editor search/navigation, (b) make merge conflicts more likely (everyone touches the same file), (c) obscure the per-concern boundaries — a new contributor has no signal that "Overview builders" vs "DRE builders" are logically separate.
> - **Fix:** When a module exceeds ~1000 lines, split into a package. One file per concern. `__init__.py` re-exports all public symbols for backward compat (so existing `from foo.bar import X` imports continue to work — zero downstream changes). The financials v2.0 split created 13 files in `report/`: `__init__.py` (re-exports) + `_helpers.py` (shared primitives + constants) + 11 per-tab builders (`overview.py`, `indicadores.py`, `crescimento.py`, `statements.py`, `balanco.py`, `dre.py`, `dfc.py`, `dva.py`, `analysis.py`, `periods.py`, `error.py`). Same pattern as `valuation` v2.0 + `skills/cvm/calculations/engines/<stmt>/` subfolders.

---

*Last updated: 2026-08-13 (v2.0 — report/ package split + v1.25 cache/ITR/CAGR/chart-toggle lessons + v2.0 split-pattern lesson). See [CHANGELOG.md](CHANGELOG.md) for version history.*
