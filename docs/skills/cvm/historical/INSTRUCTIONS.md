<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never import a metric from an engine** — Engines are below metrics in the dependency graph. A metric imports engines; never the reverse. Violating this creates circular dependencies.
2. **Never query CVM/B3 directly from a metric** — That's the engine's job. Metrics compose engines; they don't fetch data. If you need a new data source, add an ENGINE first, then import it from the metric.
3. **Never name an engine after a ratio** — `engines/vpa.py` is WRONG. VPA is a ratio (metric), not a raw quantity. The engine produces PL (a raw quantity); the metric computes P/VPA from it. See naming convention below.
4. **Never compute TTM/PL for each day individually** — TTM changes quarterly, PL changes quarterly, shares change annually. Use `*_periods()` to get the step function, then do O(1) lookups per day.
5. **Never forget `parse_escala`** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Always apply `parse_escala(r["escala"])` before using values.
6. **Never return P/L when earnings <= 0, or P/VPA when PL <= 0** — Ratios are meaningless with negative denominators. Return None (chart shows gaps).
7. **Never hardcode empresa_ids** — DFP and ITR have independent autoincrement IDs. Always call `resolve_company()` separately for each database.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite entire files** — surgical edits only.
10. **Never print to stdout** — MCP stdio corruption.
11. **Never register engines in a dict** — engines are imported by name by metrics. Only METRICS have a registry (`metrics/__init__.py` METRICS dict).
12. **Never import metric modules at the top of `historical.py`** — use lazy imports inside functions (`from skills.cvm.historical.metrics.pe import ...` inside `pe_history()`). This keeps `core.config` from loading at test collection time.

---

## ✅ ALWAYS DO

1. **Always resolve empresa_ids separately for DFP and ITR** — They are separate SQLite files with independent autoincrement IDs. Using DFP's IDs to query ITR returns wrong/empty rows.
2. **Always use step-function optimization** — Precompute TTM/PL/shares periods, then lookup per day. Don't recompute for 1200 days.
3. **Always add `data_freshness`** — Use `add_freshness(result)` from `_freshness.py`.
4. **Always run `compileall` before `pytest`** — catches syntax errors early.
5. **Always follow the engine contract** — `<quantity>_at(company, date) -> float | None` + `<quantity>_periods(company) -> list[dict]`. Every engine must have both functions.
6. **Always follow the metric contract** — `<name>_at(company, date) -> float | None` + `<name>_history(company, date_from, date_to) -> list[dict]`. Every metric must have both functions.
7. **Always register new metrics in the METRICS dict** (`metrics/__init__.py`) — so `ratio_history()` and external callers can discover them.
8. **Always wire new metrics into `_metric_dispatch()`** in `historical.py` — so `summary()` becomes metric-aware automatically.
9. **Always mock the engines (not the DB) in metric tests** — patch `skills.cvm.historical.metrics.<name>.<engine_fn>`. This isolates the ratio math from the data layer.
10. **Always update the adapter count test** when adding a new adapter — `tests/tools/report/test_report_adapters.py` `test_adapters_registered` hardcodes the count.
11. **Always document the engine in `engines/__init__.py`** inventory when adding one.
12. **Always update CHANGELOG.md** when adding metrics/engines/modes — see `docs/DOCUMENTATION_GUIDE.md`.

---

## 📐 Naming Convention

| Layer | File name | Based on | Example |
|-------|-----------|----------|---------|
| Engine | `<quantity>.py` | The raw quantity it produces | `price.py`, `earnings.py`, `shares.py`, `pl.py` |
| Metric | `<ratio>.py` | The ratio abbreviation (lowercase) | `pe.py` (P/L), `vpa.py` (P/VPA), `ev_ebitda.py` (EV/EBITDA) |

**Rule:** Engine file names are nouns (the quantity). Metric file names are ratio abbreviations. Never mix them — `engines/vpa.py` or `metrics/pl.py` are both WRONG.

---

## 📐 Dependency Graph Rule

```
historical.py  (orchestrator — knows both layers)
       ↓
    metrics/    (ratios — import engines, never each other)
       ↓
    engines/    (basics — import data sources, never each other, never metrics)
       ↓
data_sources/   (CVM/B3 DB access)
```

**Acyclic. Always points downward.** If you find yourself wanting an engine to import a metric, or a metric to import another metric, stop — you're creating coupling. Refactor instead.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.1 — Engine/metric name confusion
> - **What happened:** The original stub was named `metrics/pvpa.py`, but when implementing it, the instinct was to create `engines/vpa.py`. This mixes the layers — VPA is a ratio (metric), not a raw quantity. The raw quantity is PL (Patrimônio Líquido).
> - **Why it matters:** If engines and metrics share names, the dependency graph becomes ambiguous. Future contributors won't know whether `vpa` refers to the engine or the metric. The backtest skill reuses engines — it needs to import `pl_at()`, not `vpa_at()` (which is a ratio requiring price + shares too).
> - **Fix:** Engine produces PL → `engines/pl.py` with `pl_at()` / `pl_periods()`. Metric computes P/VPA → `metrics/vpa.py` with `vpa_at()` / `vpa_history()`. Clear separation. Documented the naming convention in INSTRUCTIONS + ARCHITECTURE.

### v1.0 — FRE shares NULL (investsite fallback)
> - **What happened:** FRE `distribuicao_capital.qtd_total_circulacao` is NULL for every row in the synced database. Without shares, P/L cannot be computed and every historical day returns None (chart renders blank).
> - **Why it matters:** The chart was blank even though the code was correct — the data source was the problem.
> - **Fix:** Added investsite.com.br fallback in `engines/shares.py`. The value is cached and treated as constant across all historical dates (shares change infrequently — annually at most).

### v1.0 — TTM derivation edge cases
> - **What happened:** TTM derivation has multiple edge cases: no ITR before date (fall back to DFP annual), no ITR for prior year same period (use DFP directly), no DFP for prior year (can't derive TTM).
> - **Why it matters:** Missing these edge cases returns None for legitimate dates.
> - **Fix:** `ttm_earnings_at()` handles all 4 cases with explicit branches. Tests cover each path.

---

*Last updated: 2026-07-26 (v1.1 — engine/metric separation). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history.*
