<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill** — Skills are read-only. They call data_source query engines. Sync belongs in `data_sources/`.
2. **Never use `float(escala)` directly** — DFP stores escala as Portuguese words ("MIL", "MILHOES"). Always use `parse_escala()` from `_db.py`.
3. **Never return cumulative values as standalone** — ITR values are cumulative. Flow items (DRE/DFC/DVA) must be subtracted to get standalone quarters. Snapshot items (BPA/BPP) use period-end value directly.
4. **Never change the EBITDA formula** — `EBITDA = EBIT (DRE 3.05) + D&A (DFC 6.01.01.02)`. The D&A comes from the cash flow statement, not the DRE.
5. **Never change the Q4 derivation** — `Q4 = DFP annual (meses=12) − ITR Q3 cumulative (meses=9)`. This requires both DFP + ITR to be synced.
6. **Never replace `compute_ratios()` with calculations metrics in `quarterly`/`annual`/`complete` modes** — Calculations engines are point-in-time (`*_at(company, date)`); per-period rendering needs ratios from raw `{codigo: valor}` dicts. The two patterns coexist intentionally. Calculations integration is confined to `summary()` `current_ratios` only.
7. **Never import calculations metrics at the top of `financials.py`** — Lazy-import them inside `summary()` so importing the module doesn't trigger the calculations registry (and the `PLANNER_MODEL` env-var requirement).
8. **Never call a calculations metric without `_safe_call`** — Engines may raise `FileNotFoundError` when their underlying DB (cotahist, fre, itr) is not synced. Without the wrapper, one missing DB crashes the whole `summary()`.
9. **Never create `.bak` files** — Forbidden by project rules.
10. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
11. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `parse_escala()` for escala values** — `float("MIL")` crashes.
2. **Always make summary sections best-effort** — If one data source is missing, the summary should still return what's available.
3. **Always annualize ROA/ROE for quarterly** — `lucro_liquido * 4 / ativo_total`. Document that TTM is on the roadmap.
4. **Always return `period_type` in the result** — So callers know if it's "annual" or "quarterly".
5. **Always sort periods newest-first** — Consistent with other skills.
6. **Always run `compileall` before `pytest`** — Catches syntax errors early.
7. **Always split tests by mode** — `test_metrics.py` / `test_annual.py` / `test_quarterly.py` / `test_complete.py` / `test_summary.py` / `test_route.py` + shared `conftest.py`. One test class per file (regression classes allowed as additional classes in the same file).

---

### Anti-patterns & Lessons Learned

#### v1.3 — Per-period modes can't use calculations engines
> - **What happened:** Initial Phase 3 plan considered replacing `compute_ratios()` with calculations metric calls inside `quarterly()` / `annual()` / `complete()`.
> - **Why it matters:** Calculations engines are point-in-time (`*_at(company, date)` returns ONE value for a given date). Statement-rendering modes need per-period ratios (one ratio per quarter/year, for N periods). Calling calculations per period would re-query DFP/ITR N times via `connect_dfp`/`connect_itr` — wasteful, when the dict is already in memory.
> - **Fix:** Calculations integration is confined to `summary()` `current_ratios` (a single point-in-time snapshot). Per-period modes keep their own `compute_ratios(metrics, is_quarterly)` that operates on the already-fetched `{codigo: valor}` dict. The two patterns coexist intentionally. Documented in NEVER DO #6.

#### v1.3 — Lazy import protects module load from registry initialization
> - **What happened:** Initial draft imported calculations metrics at the top of `financials.py`. Importing the module then triggered `skills.cvm.calculations._registry` auto-discovery, which transitively imports `core.config`, which requires `PLANNER_MODEL` env var. Importing financials.py for a quick smoke test would crash with `RuntimeError: PLANNER_MODEL is required`.
> - **Why it matters:** Skills should be importable without runtime env vars (tests, lint, introspection). Pulling in the calculations registry at module-load time breaks that invariant.
> - **Fix:** Lazy-import calculations metrics inside `summary()` function body. Module load no longer touches the calculations registry. Tests that don't call `summary()` stay fast (no registry init). Documented in NEVER DO #7.
