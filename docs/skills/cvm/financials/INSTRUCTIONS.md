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

---

*Last updated: 2026-08-01 (v1.16 — dashboard v3 bugfix sprint). See [CHANGELOG.md](CHANGELOG.md) for version history.*
