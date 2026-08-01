<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🛡️ AI Instructions

**This skill is a thin wrapper over the shared `calculations/` package.** Engine/metric/registry editing rules live in [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md) — read those FIRST. This doc covers only the historical-specific rules on top.

**Current scope (v1.2):** Engines + metrics live in `calculations/`. Historical exposes 40 modes total: 37 auto-generated `<metric>_history` (one per metric in calculations) + 3 explicit (`ratio_history`, `summary`, `dashboard`). Source is modularized as `_registry.py` + `modes/` + `helpers.py` + `report.py` (the monolithic `historical.py` was decomposed in v1.2).

## ❌ NEVER DO

**Engine/metric/registry rules are owned by calculations/** — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-never-do) for the 25 NEVER DO rules there. The rules below are historical-specific.

1. **Never add engines or metrics to `skills/cvm/historical/`** — they belong in `skills/cvm/calculations/`. The historical skill is now a thin consumer of calculations; it has no `engines/` or `metrics/` subfolders. Adding them there defeats the purpose of the shared calculations package.
2. **Never import engines or metrics directly in `historical/modes/*.py` at module top** — use the registry (`resolve_metric()`) for metric resolution. The only top-level import from calculations should be: `from skills.cvm.calculations._registry import METRICS, ENGINES, resolve_metric, list_metrics, list_engines`.
3. **Never manually edit `historical/__init__.py` to add a `<metric>_history` mode** — the MANIFEST auto-generates from the calculations registry. Adding a metric to calculations = a new mode appears in historical automatically.
4. **Never manually edit `adapters/historical.py` to add a chart adapter** — chart adapters auto-register from the calculations registry. The `historical_<metric>_chart` adapter appears automatically (dual-axis if `per_share_label` is set, single-dataset if `None`).
5. **Never duplicate an engine or metric in historical** — if historical needs an engine or metric that already exists in calculations, import it. Don't reimplement. If you need a slightly different behavior, add a new engine/metric to calculations with a different name.
6. **Never compute TTM/snapshot/multi-code/description-search algorithms in historical** — those live in calculations engines. Historical's `summary()` owns only percentile analysis (rank + thresholds). Everything else delegates to `spec.history_fn`.
7. **Never edit `modes/summary.py`'s `_metric_history()` to special-case a specific metric** — all metric dispatch goes through `resolve_metric()` + `spec.history_fn()`. The function is metric-agnostic.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite entire files** — surgical edits only.
10. **Never print to stdout** — MCP stdio corruption.

---

## ✅ ALWAYS DO

**Engine/metric/registry rules are owned by calculations/** — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-always-do) for the 18 ALWAYS DO rules there. The rules below are historical-specific.

1. **Always import registry helpers from calculations** — `from skills.cvm.calculations._registry import METRICS, ENGINES, resolve_metric, list_metrics, list_engines`. NOT from any historical-internal location (the historical skill no longer has a `_registry.py`).
2. **Always use `resolve_metric()` for metric resolution in `ratio_history()` + `summary()`** — it handles canonical names + aliases + case-insensitivity. Never import individual metric modules.
3. **Always wrap metric `history_fn` results with `add_freshness()`** — `historical.py:_metric_history()` calls `add_freshness(result)` before returning. Freshness metadata is consumer-facing.
4. **Always run `compileall` before `pytest`** — catches syntax errors early.
5. **Always count `ratio_days` (non-None ratio entries) in `_metric_history()`** — the response includes `f"{spec.ratio_key}_days"` so consumers know how many valid ratio data points exist (vs total days). Negative earnings years return None for the ratio — those don't count.
6. **Always keep `summary()` metric-aware via `spec.per_share_label`** — skip per-share KPI/row when `per_share_label` is `None` (fundamental ratios). The summary table renders differently for Type 1 vs Type 2 metrics.
7. **Always mock the registry spec in tests** — `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Not the module function. This works because `_metric_history()` calls `spec.history_fn` (captured at registration time).
8. **Always update the adapter count test in `tests/tools/report/test_report_adapters.py`** when a new metric is added to calculations — `test_adapters_registered` hardcodes the count of `historical_*_chart` adapters. Adding a metric to calculations = +1 adapter here.
9. **Always update `docs/skills/cvm/historical/CHANGELOG.md`** when a metric is added to calculations (consumer-visible change: new `<metric>_history` mode appears in historical MANIFEST). ALSO update `docs/skills/cvm/calculations/CHANGELOG.md` for the calculations-internal change.
10. **Always keep percentile interpretation thresholds consistent** — ≤ 25th = cheap, 25-75th = fair, ≥ 75th = expensive. Documented in [API.md](API.md) + [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 📐 Naming Convention

Engine + metric naming conventions are owned by calculations — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-naming-convention). Historical follows the same conventions (it has no engines or metrics of its own to name).

Historical's own naming is simple:
- **Modes:** `<metric>_history` (auto-generated from `METRICS`), `ratio_history` (generic), `summary` (generic). Always lowercase, snake_case.
- **Adapters:** `historical_<metric>_chart` (auto-registered from `METRICS`), `historical_summary` (metric-aware). Always prefixed with `historical_` to namespace from other skills' adapters.

---

## 📐 Metric Types

Metric types are owned by calculations — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-metric-types). Historical handles both types uniformly via `spec.per_share_key` None-checks in `_metric_history()` + `summary()` + the chart adapters.

---

## 📐 Dependency Graph Rule

The dependency graph is owned by calculations — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-dependency-graph-rule). Historical sits at the consumer layer:

```
historical/modes/ + helpers.py  (consumer orchestrator — reads from calculations registry)
       │
       └── skills.cvm.calculations._registry
              │
              ├── calculations/engines/  (engines — LEAVES)
              └── calculations/metrics/   (metrics — compose engines)
```

Historical never imports individual engines or metrics — only the registry helpers. All metric dispatch goes through `resolve_metric()` + `spec.history_fn()`.

---

## 📐 Auto-Discovery Rules

Auto-discovery is owned by calculations — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-auto-discovery-rules). Historical has no auto-discovery of its own. It relies on calculations' `_auto_discover()` to populate `ENGINES` + `METRICS` at import time, then iterates `METRICS` to generate modes + adapters.

Historical's auto-generation chain (in `historical/__init__.py` + `modes/` + `helpers.py` + `adapters/historical.py`):
1. `_build_metric_modes()` in `historical/__init__.py` — iterates `METRICS` from calculations registry, generates one `<metric>_history` mode entry per metric.
2. `_make_metric_history_fn()` in `helpers.py` (extracted in v1.2) — generates `<metric>_history` functions into `globals()` at import time. Each is a thin wrapper around `_metric_history()`.
3. `adapters/historical.py` — iterates `METRICS`, registers `historical_<metric>_chart` adapter for each. Inspects `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
4. `modes/dashboard.py` (v1.2) — thin pass-through that aggregates per-metric summaries into a multi-tab dashboard payload for the `historical_dashboard` adapter.

**Adding a metric to calculations = a new mode + a new adapter appear in historical automatically.** Zero edits to historical source files.

---

## 🚫 Anti-Patterns & Lessons Learned

**Engine/metric/registry anti-patterns are owned by calculations/** — see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-anti-patterns--lessons-learned) for the full list (Phase 1 extraction motivation, ROIC+cash, fundamental ratios + None per-share, manual inventory, frozen MetricSpec, name confusion, FRE NULL, TTM edge cases).

Historical-specific lessons:

### v2.2 — Phase 1 refactor motivation
> - **What happened:** Before v1.11, engines + metrics + the registry lived inside `skills/cvm/historical/`. The historical skill was both a consumer skill (with modes + adapters) AND the canonical home for the engine/metric library. Other CVM skills (valuation, financials) that needed the same engines either duplicated the logic or imported from `skills.cvm.historical.engines.*` — coupling themselves to the historical skill's mode dispatch.
> - **Why it matters:** Duplication drifts over time. Coupling to a consumer skill for shared logic means changing the historical skill's modes can break unrelated skills.
> - **Fix:** Extracted engines + metrics + registry into `skills/cvm/calculations/` — a pure library with no modes, no MANIFEST, no adapters. Historical is now a thin consumer. Other CVM skills can import from calculations without coupling to historical. Documented in INSTRUCTIONS rules #1 + #5 (NEVER) + [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md) rules #24 + #25.

### v1.0 — Percentile analysis stays in historical
> - **What happened:** Early in v1.0, there was discussion about whether percentile analysis (cheap/fair/expensive thresholds) belonged in the registry or in the consumer skill.
> - **Why it matters:** Percentile analysis is a consumer concern — different consumers may want different summary styles (e.g., backtest might want return percentiles, not ratio percentiles). Putting it in the registry would couple the library to one summary style.
> - **Fix:** Percentile analysis lives in `historical.py:summary()` only. The registry + calculations package has no percentile logic. This is the canonical reason historical exists as a separate skill from calculations.

- **v1.13 lesson:** _registry.py + __init__.py now delegate to `skills/_base.py` (shared ModeSpec + make_registry + make_route + auto_discover_modes). The duplicated ~97-line _registry.py + ~88-line __init__.py boilerplate is gone — each skill's _registry.py is now ~16 lines, __init__.py is ~50 lines. Historical's `_auto_register_metric_history_modes()` (which auto-registers `<metric>_history` modes from calculations METRICS) was PRESERVED — historical-only logic not in `_base.py`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)` (unchanged). Adding a new skill = 3 files (_registry.py + __init__.py + modes/) following the pattern in [SKILLS.md → How to Create a New Skill](../../SKILLS.md). Bug fixes to the dispatch infrastructure now only need to be made in ONE place.

---

## 📐 Pattern Template Checklist (when copying to a new skill)

The pattern template is now **calculations**, not historical. See [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md#-pattern-template-checklist-when-copying-to-a-new-skill) for the 10-item checklist. Historical is a consumer of calculations, not a template itself.

If you're creating a new consumer skill (like historical) that wraps calculations, the consumer-specific checklist is:

- [ ] `__init__.py` (skill manifest) — MANIFEST modes auto-generate from calculations registry (`_build_metric_modes()` iterates `METRICS` from `skills.cvm.calculations._registry`).
- [ ] `<skill>.py` — `_metric_history()` reads from calculations registry, auto-generates `<metric>_history` functions. Handle BOTH Type 1 and Type 2 metrics via `spec.per_share_key` None-check.
- [ ] `adapters/<skill>.py` — chart adapters auto-register from calculations registry. Inspect `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
- [ ] Tests mock the calculations registry spec (not the module function): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`.
- [ ] Docs reference calculations for engine/metric/registry details; document only the consumer-specific layer (modes, summary style, adapters).

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; `_auto_register_metric_history_modes()` preserved). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history, [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md) for engine/metric/registry editing rules.*
