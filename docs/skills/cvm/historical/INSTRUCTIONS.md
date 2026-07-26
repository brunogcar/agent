<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🛡️ AI Instructions

This skill is the **pattern template** for auto-discovery + registry architecture. Follow these rules when editing this skill OR when copying the pattern to a new skill.

## ❌ NEVER DO

1. **Never import a metric from an engine** — Engines are below metrics in the dependency graph. A metric imports engines; never the reverse. Violating this creates circular dependencies.
2. **Never query CVM/B3 directly from a metric** — That's the engine's job. Metrics compose engines; they don't fetch data. If you need a new data source, add an ENGINE first, then import it from the metric.
3. **Never name an engine after a ratio** — `engines/vpa.py` is WRONG. VPA is a ratio (metric), not a raw quantity. The engine produces PL (a raw quantity); the metric computes VPA from it. See naming convention below.
4. **Never name a metric after a raw quantity** — `metrics/pl.py` is WRONG. PL is a raw quantity (engine). The metric computes a ratio from PL. Use the per-share quantity name: `metrics/vpa.py` (VPA = PL/shares).
5. **Never compute TTM/PL for each day individually** — TTM changes quarterly, PL changes quarterly, shares change annually. Use `*_periods()` to get the step function, then do O(1) lookups per day.
6. **Never forget `parse_escala`** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Always apply `parse_escala(r["escala"])` before using values.
7. **Never return a ratio when the denominator <= 0** — P/L with negative earnings, P/VPA with negative equity, Payout with negative earnings. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
8. **Never hardcode empresa_ids** — DFP and ITR have independent autoincrement IDs. Always call `resolve_company()` separately for each database.
9. **Never create `.bak` files** — forbidden by project rules.
10. **Never rewrite entire files** — surgical edits only.
11. **Never print to stdout** — MCP stdio corruption.
12. **Never put auto-discovery code in `engines/__init__.py` or `metrics/__init__.py`** — auto-discovery is in the CENTRAL `_registry.py` (top level). The `__init__.py` files in `engines/` and `metrics/` are minimal docstrings.
13. **Never import metric modules at the top of `historical.py`** — use the registry (`resolve_metric()`). The registry handles lazy resolution.
14. **Never manually edit `__init__.py` to add a `<metric>_history` mode** — the MANIFEST auto-generates from the registry. Adding a metric = drop a file + `register_metric()`.
15. **Never manually edit `adapters/historical.py` to add a chart adapter** — chart adapters auto-register from the registry. The `historical_<metric>_chart` adapter appears automatically.
16. **Never put non-metric files in `metrics/`** — auto-discovery imports everything (except `__init__.py`). Utility modules will break the registry. The `_registry.py` is at the TOP level, not in `metrics/`.
17. **Never put non-engine files in `engines/`** — auto-discovery imports everything (except `__init__.py`). Utility modules will be imported as engines.
18. **Never make `MetricSpec` or `EngineSpec` frozen** — tests need to monkeypatch `spec.history_fn` / `spec.at_fn`. Use `@dataclass` (not `@dataclass(frozen=True)`).
19. **Never mock the module function in tests** — `_metric_history()` calls `spec.history_fn` (captured at registration time). Mock the registry spec: `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`.
20. **Never re-run auto-discovery** — `_auto_discover()` is idempotent (uses a `_done` flag). Don't call it manually; it runs once at import time.

---

## ✅ ALWAYS DO

1. **Always resolve empresa_ids separately for DFP and ITR** — They are separate SQLite files with independent autoincrement IDs. Using DFP's IDs to query ITR returns wrong/empty rows.
2. **Always use step-function optimization** — Precompute TTM/PL/shares periods, then lookup per day. Don't recompute for 1200 days.
3. **Always add `data_freshness`** — Use `add_freshness(result)` from `_freshness.py`.
4. **Always run `compileall` before `pytest`** — catches syntax errors early.
5. **Always follow the engine contract** — `<quantity>_at(company, date) -> float | None` + `<quantity>_periods(company) -> list[dict]` + `register_engine(EngineSpec(...))` at module level. Every engine must have all three.
6. **Always follow the metric contract** — `<name>_at(company, date)` (per-share) + `<ratio>_at(company, date)` (ratio) + `<name>_history(company, date_from, date_to)` + `register_metric(MetricSpec(...))` at module level. Every metric must have all four.
7. **Always call `register_engine()` / `register_metric()` at module level** — so the engine/metric auto-registers when the module is imported by auto-discovery.
8. **Always include aliases** — `["pe", "pl", "p/l"]` for lpa, `["dy", "dividend_yield", "yld", "payout"]` for dpa. Users expect to call `summary(metric="pe")`, not just `summary(metric="lpa")`.
9. **Always produce BOTH per-share value and ratio** — LPA + P/L, VPA + P/VPA, DPA + Div Yield. The per-share value is useful on its own (backtests). The ratio tells you if the stock is cheap. Bonus ratios (e.g., Payout) are optional.
10. **Always mock the registry spec in tests** — `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Not the module function.
11. **Always update the adapter count test** when adding a new adapter — `tests/tools/report/test_report_adapters.py` `test_adapters_registered` hardcodes the count.
12. **Always document the engine in `engines/__init__.py`** inventory docstring when adding one.
13. **Always update CHANGELOG.md** when adding metrics/engines/modes — see `docs/DOCUMENTATION_GUIDE.md`.
14. **Always use `sorted()` in auto-discovery glob** — `sorted((base / "engines").glob("*.py"))` for deterministic import order across filesystems.
15. **Always import from the central `_registry.py`** — `from skills.cvm.historical._registry import MetricSpec, register_metric`. NOT from `metrics._registry` (old v1.2 location, deleted in v1.3).

---

## 📐 Naming Convention

| Layer | File name | Based on | Example |
|-------|-----------|----------|---------|
| Engine | `<quantity>.py` | The raw quantity it produces | `price.py`, `earnings.py`, `shares.py`, `pl.py` |
| Metric | `<per_share>.py` | The per-share quantity it derives | `lpa.py` (LPA = earnings/shares), `vpa.py` (VPA = pl/shares) |

**Rule:** Engine file names are nouns (the raw quantity). Metric file names are per-share quantity names. Never mix them — `engines/vpa.py` or `metrics/pl.py` are both WRONG.

**JSON keys in series entries:**
- Per-share value: metric name (`lpa`, `vpa`)
- Ratio: traditional abbreviation (`pe` for P/L, `pvpa` for P/VPA)
- Engine quantities: `price`, `ttm_earnings`, `shares`, `pl`

---

## 📐 Dependency Graph Rule

```
historical.py  (orchestrator — reads from registry, knows both layers)
       │
       ├── metrics/_registry.py  (MetricSpec registry, resolve_metric)
       │       │
       │       ├── metrics/lpa.py  ──┬── engines/price.py
       │       │                      ├── engines/earnings.py
       │       │                      └── engines/shares.py
       │       │
       │       └── metrics/vpa.py  ──┬── engines/price.py
       │                              ├── engines/pl.py
       │                              └── engines/shares.py
       │
       └── (engines never point upward — they're leaves)
```

**Acyclic. Always points downward.** If you find yourself wanting an engine to import a metric, or a metric to import another metric, stop — you're creating coupling. Refactor instead.

---

## 📐 Auto-Discovery Rules

1. **`_registry.py` (top level)** — the CENTRAL auto-discovery module. Globs `engines/*.py` AND `metrics/*.py` (excluding `__init__.py`). Imports each via `importlib.import_module()`. This triggers `register_engine()` and `register_metric()` calls. Idempotent (uses `_done` flag).
2. **`engines/__init__.py`** — minimal docstring (NO auto-discovery code). Auto-discovery is in the central `_registry.py`.
3. **`metrics/__init__.py`** — minimal docstring (NO auto-discovery code). Auto-discovery is in the central `_registry.py`.
4. **`adapters/historical.py`** — iterates over `METRICS` dict and auto-registers chart adapters via `ADAPTERS[f"historical_{name}_chart"] = _adapter_fn`.
5. **`__init__.py`** (skill manifest) — `_build_metric_modes()` iterates over `METRICS` and generates `<metric>_history` mode entries for the MANIFEST.
6. **`historical.py`** — `_make_metric_history_fn()` generates `<metric>_history` functions and assigns them to `globals()`.

**Adding a metric = 1 file in `metrics/` + `register_metric()`.** Everything else auto-generates.
**Adding an engine = 1 file in `engines/` + `register_engine()`.** It's immediately available for metrics to import.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.3 — Registry scattered across subfolders
> - **What happened:** In v1.2, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.
> - **Why it matters:** The pattern wasn't consistent. `list_engines()` didn't exist, so the backtest skill couldn't discover engines programmatically. Adding an engine required editing metrics that needed it, with no central inventory.
> - **Fix:** Moved `_registry.py` to the skill top level (`skills/cvm/historical/_registry.py`). It now handles BOTH engines and metrics auto-discovery. New `EngineSpec` dataclass + `register_engine()`. Both layers self-register. `list_engines()` enables backtest discovery. `engines/__init__.py` and `metrics/__init__.py` simplified to minimal docstrings.

### v1.2 — Frozen MetricSpec broke tests
> - **What happened:** `MetricSpec` was `@dataclass(frozen=True)`. Tests tried to `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)` to mock the history function. Frozen dataclasses raise `FrozenInstanceError` on setattr.
> - **Why it matters:** `_metric_history()` calls `spec.history_fn` (captured at registration time). If we can't patch the spec, we can't mock the history function in tests. Patching the module function (`metrics.lpa.lpa_history`) doesn't work because the spec already holds a reference to the original.
> - **Fix:** Changed `MetricSpec` to `@dataclass` (not frozen). Tests now patch `METRICS["lpa"].history_fn` directly. Documented in INSTRUCTIONS rule #18 + #19.

### v1.2 — Engine/metric name confusion (from v1.1)
> - **What happened:** The original stub was named `metrics/pvpa.py`, but when implementing it, the instinct was to create `engines/vpa.py`. This mixes the layers — VPA is a ratio (metric), not a raw quantity. The raw quantity is PL (Patrimônio Líquido).
> - **Why it matters:** If engines and metrics share names, the dependency graph becomes ambiguous. Future contributors won't know whether `vpa` refers to the engine or the metric. The backtest skill reuses engines — it needs to import `pl_at()`, not `vpa_at()` (which is a ratio requiring price + shares too).
> - **Fix:** Engine produces PL → `engines/pl.py` with `pl_at()` / `pl_periods()`. Metric computes P/VPA → `metrics/vpa.py` with `vpa_at()` / `pvpa_at()` / `vpa_history()`. Clear separation. Documented the naming convention.

### v1.0 — FRE shares NULL (investsite fallback)
> - **What happened:** FRE `distribuicao_capital.qtd_total_circulacao` is NULL for every row in the synced database. Without shares, P/L cannot be computed and every historical day returns None (chart renders blank).
> - **Why it matters:** The chart was blank even though the code was correct — the data source was the problem.
> - **Fix:** Added investsite.com.br fallback in `engines/shares.py`. The value is cached and treated as constant across all historical dates (shares change infrequently — annually at most).

### v1.0 — TTM derivation edge cases
> - **What happened:** TTM derivation has multiple edge cases: no ITR before date (fall back to DFP annual), no ITR for prior year same period (use DFP directly), no DFP for prior year (can't derive TTM).
> - **Why it matters:** Missing these edge cases returns None for legitimate dates.
> - **Fix:** `ttm_earnings_at()` handles all 4 cases with explicit branches. Tests cover each path.

---

## 📐 Pattern Template Checklist (when copying to a new skill)

If you're creating a new skill that follows this pattern:

- [ ] `_registry.py` (top level) — EngineSpec + MetricSpec + register_engine + register_metric + auto-discovery (globs both engines/ and metrics/) + resolve_metric + aliases
- [ ] `engines/__init__.py` — minimal docstring (NO auto-discovery code)
- [ ] `engines/<quantity>.py` — one per raw quantity, follows engine contract + `register_engine()` at module level
- [ ] `metrics/__init__.py` — minimal docstring (NO auto-discovery code)
- [ ] `metrics/<per_share>.py` — one per ratio, calls `register_metric()` at module level
- [ ] `<skill>.py` — `_metric_history()` reads from registry, auto-generates `<metric>_history` functions
- [ ] `__init__.py` (skill manifest) — MANIFEST modes auto-generate from registry
- [ ] `adapters/<skill>.py` — chart adapters auto-register from registry
- [ ] Tests mock the registry spec (not the module function)
- [ ] Docs document the central registry + engine/metric separation + auto-discovery

---

*Last updated: 2026-07-26 (v1.3 — central registry + engine self-registration + DPA metric). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history.*
