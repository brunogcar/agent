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
7. **Never return a ratio when the denominator <= 0** — P/L with negative earnings, P/VPA with negative equity. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
8. **Never hardcode empresa_ids** — DFP and ITR have independent autoincrement IDs. Always call `resolve_company()` separately for each database.
9. **Never create `.bak` files** — forbidden by project rules.
10. **Never rewrite entire files** — surgical edits only.
11. **Never print to stdout** — MCP stdio corruption.
12. **Never register engines in a dict** — engines are imported by name by metrics. Only METRICS have a registry (`metrics/_registry.py`).
13. **Never import metric modules at the top of `historical.py`** — use the registry (`resolve_metric()`). The registry handles lazy resolution.
14. **Never manually edit `__init__.py` to add a `<metric>_history` mode** — the MANIFEST auto-generates from the registry. Adding a metric = drop a file + `register_metric()`.
15. **Never manually edit `adapters/historical.py` to add a chart adapter** — chart adapters auto-register from the registry. The `historical_<metric>_chart` adapter appears automatically.
16. **Never put non-metric files in `metrics/`** — auto-discovery imports everything (except `__init__.py` and `_registry.py`). Utility modules will break the registry.
17. **Never put non-engine files in `engines/`** — auto-discovery imports everything (except `__init__.py`). Utility modules will be imported as engines.
18. **Never make `MetricSpec` frozen** — tests need to monkeypatch `spec.history_fn`. Use `@dataclass` (not `@dataclass(frozen=True)`).
19. **Never mock the module function in tests** — `_metric_history()` calls `spec.history_fn` (captured at registration time). Mock the registry spec: `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`.

---

## ✅ ALWAYS DO

1. **Always resolve empresa_ids separately for DFP and ITR** — They are separate SQLite files with independent autoincrement IDs. Using DFP's IDs to query ITR returns wrong/empty rows.
2. **Always use step-function optimization** — Precompute TTM/PL/shares periods, then lookup per day. Don't recompute for 1200 days.
3. **Always add `data_freshness`** — Use `add_freshness(result)` from `_freshness.py`.
4. **Always run `compileall` before `pytest`** — catches syntax errors early.
5. **Always follow the engine contract** — `<quantity>_at(company, date) -> float | None` + `<quantity>_periods(company) -> list[dict]`. Every engine must have both functions.
6. **Always follow the metric contract** — `<name>_at(company, date)` (per-share) + `<ratio>_at(company, date)` (ratio) + `<name>_history(company, date_from, date_to)`. Every metric must have all three functions.
7. **Always call `register_metric()` at module level** — so the metric auto-registers when the module is imported by auto-discovery.
8. **Always include aliases** — `["pe", "pl", "p/l"]` for lpa. Users expect to call `summary(metric="pe")`, not just `summary(metric="lpa")`.
9. **Always produce BOTH per-share value and ratio** — LPA + P/L, VPA + P/VPA. The per-share value is useful on its own (backtests). The ratio tells you if the stock is cheap.
10. **Always mock the registry spec in tests** — `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Not the module function.
11. **Always update the adapter count test** when adding a new adapter — `tests/tools/report/test_report_adapters.py` `test_adapters_registered` hardcodes the count.
12. **Always document the engine in `engines/__init__.py`** inventory when adding one.
13. **Always update CHANGELOG.md** when adding metrics/engines/modes — see `docs/DOCUMENTATION_GUIDE.md`.
14. **Always use `sorted()` in auto-discovery glob** — `sorted(Path(__file__).parent.glob("*.py"))` for deterministic import order across filesystems.

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

1. **`engines/__init__.py`** — globs `*.py` (excluding `__init__.py`). Imports each via `importlib.import_module()`. No registry, no decorator. Engines are imported by name by metrics.
2. **`metrics/__init__.py`** — globs `*.py` (excluding `__init__.py` and `_registry.py`). Imports each via `importlib.import_module()`. This triggers `register_metric()` in each metric module.
3. **`adapters/historical.py`** — iterates over `METRICS` dict and auto-registers chart adapters via `ADAPTERS[f"historical_{name}_chart"] = _adapter_fn`.
4. **`__init__.py`** — `_build_metric_modes()` iterates over `METRICS` and generates `<metric>_history` mode entries for the MANIFEST.
5. **`historical.py`** — `_make_metric_history_fn()` generates `<metric>_history` functions and assigns them to `globals()`.

**Adding a metric = 1 file + `register_metric()`.** Everything else auto-generates.

---

## 🚫 Anti-Patterns & Lessons Learned

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

- [ ] `engines/__init__.py` — auto-discovery via glob + importlib
- [ ] `engines/<quantity>.py` — one per raw quantity, follows engine contract
- [ ] `metrics/__init__.py` — auto-discovery via glob + importlib
- [ ] `metrics/_registry.py` — spec dataclass + register + resolve + aliases
- [ ] `metrics/<per_share>.py` — one per ratio, calls `register_metric()` at module level
- [ ] `<skill>.py` — `_metric_history()` reads from registry, auto-generates `<metric>_history` functions
- [ ] `__init__.py` — MANIFEST modes auto-generate from registry
- [ ] `adapters/<skill>.py` — chart adapters auto-register from registry
- [ ] Tests mock the registry spec (not the module function)
- [ ] Docs document the engine/metric separation + auto-discovery + registry

---

*Last updated: 2026-07-26 (v1.2 — auto-discovery + registry). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history.*
