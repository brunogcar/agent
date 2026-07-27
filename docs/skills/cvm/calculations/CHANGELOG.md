<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.1** | 2026-07-26 | **Phase 2A: 2 new engines + 4 new metrics.** New engines: `operating_cf.py` (DFC 6.01 FCO TTM), `investing_cf.py` (DFC 6.02 FCI TTM). New metrics: `p_ebit.py` (EBIT/share + P/EBIT), `p_fco.py` (FCO/share + P/FCO), `p_fcf.py` (FCF/share + P/FCF, FCF=FCO+FCI computed internally), `graham_number.py` (Graham Number = sqrt(22.5 * LPA * VPA), fundamental). Now 18 engines + 21 metrics. |
| **v1.0** | 2026-07-26 | **Extracted from historical v2.1.** 16 engines + 17 metrics + central `_registry.py` moved to `skills/cvm/calculations/`. All import paths updated to `skills.cvm.calculations.*`. Historical skill imports engines + metrics + registry from calculations. Test files split by metric name (not version/tier) and moved to `tests/skills/cvm/calculations/` (one `test_<metric>.py` per metric, plus `test_engines.py` + `test_registry.py`). Historical skill tests slimmed to `test_historical.py` only (mode dispatch, MANIFEST, route). 355 tests pass. This is the pattern template for the central auto-discovery + registry architecture — see [INSTRUCTIONS.md](INSTRUCTIONS.md) for the pattern template checklist. |

> **Content moved from historical v2.2 docs:** All engine/metric architecture content (engine vs metric pattern, dependency graph, central auto-discovery design, key design patterns, algorithms — TTM derivation, snapshot lookup, multi-code sum, description-based search, ROIC cash subtraction, ev_ebitda data flow, how-to guides), engine/metric API tables (full function signatures for all 16 engines + 17 metrics, registry API), and engine/metric AI editing rules (NEVER DO, ALWAYS DO, naming convention, dependency graph rule, auto-discovery rules, anti-patterns v1.2–v1.9) now live in the calculations docs. The historical docs were slimmed to skill-specific content only (mode dispatch, percentile analysis, summary interpretation, MANIFEST auto-generation). See [historical/CHANGELOG.md](../historical/CHANGELOG.md) for the historical v2.2 entry that documents this split.

---

### ⚠️ Breaking Changes

*(None in v1.0. The v1.0 extraction moved source code without changing function signatures, registry API, or behavior. Only import paths changed — all `skills.cvm.historical.*` import paths for engines/metrics/registry now point to `skills.cvm.calculations.*`. Consumer code that imported from historical's `engines/` or `metrics/` subfolders must update import paths.)*

---

## 🔄 In Progress / Next Up

*(Fill this section with relevant info as the calculations library grows. New tiers of metrics/engines will be added here as they're planned.)*

- **Phase 2 (valuation skill)**: ✅ Done (v1.1 / valuation v1.1, 2026-07-26). Valuation now imports engines + metrics directly.
- **Phase 3 (financials skill)**: ✅ Done (financials v1.3, 2026-07-27). Financials `summary()` mode delegates point-in-time ratios (ROIC, Graham, EV/EBITDA, P/FCF, P/EBIT, P/FCO) to calculations metrics via lazy imports wrapped in `_safe_call`. Per-period rendering modes (`quarterly`/`annual`/`complete`) keep their own `compute_ratios()` — they operate on raw statement dicts per period, not point-in-time engine snapshots. The two patterns coexist intentionally.
- **Phase 4 (backtest skill)**: backtest skill will use `list_engines(category=...)` for signal discovery + `*_at()` / `*_periods()` for step-function optimization.

---

## 🚫 Deferred / Out of Scope

- **Subfolders for engines by category** — `engines/dre/`, `engines/bpa/`, etc. Deferred until 20+ engines. Currently 16 engines in 6 categories, organized via the `category` field on `EngineSpec` instead.
- **Type 3 metrics (per-share only, no price ratio)** — `MetricSpec` already supports this shape (`ratio_*` fields would be `None`), but no metrics use it yet. Will be added when a real use case emerges (e.g., a custom per-share quantity with no natural price ratio).
- **Shared registry helper across skills** — each skill has its own `_registry.py`. A shared helper was considered but rejected: each skill's registry has skill-specific concerns (categories, metric types) and a shared helper would create coupling. The pattern is copy-paste, not DRY.
- **Caching at the engine layer** — engines re-query the DB on every `*_at()` call. Caching (LRU on `(ticker, date)` or preloaded step functions) is deferred until profiling shows it's needed. Current step-function optimization via `*_periods()` is fast enough.

---

*Last updated: 2026-07-27 (v1.0 + Phase 3 financials integration). See [ARCHITECTURE.md](ARCHITECTURE.md) for design, [API.md](API.md) for function signatures, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
