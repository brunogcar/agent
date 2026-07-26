<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🛡️ AI Instructions

This skill is the **pattern template** for auto-discovery + registry architecture. Follow these rules when editing this skill OR when copying the pattern to a new skill.

**Current scope (v1.9):** 13 engines in 6 categories (market, shares, dre, bpa, bpp, dfc) + 10 metrics in 2 types (per-share+ratio and fundamental ratio).

## ❌ NEVER DO

1. **Never import a metric from an engine** — Engines are below metrics in the dependency graph. A metric imports engines; never the reverse. Violating this creates circular dependencies.
2. **Never query CVM/B3 directly from a metric** — That's the engine's job. Metrics compose engines; they don't fetch data. If you need a new data source, add an ENGINE first, then import it from the metric.
3. **Never name an engine after a ratio** — `engines/vpa.py` is WRONG. VPA is a ratio (metric), not a raw quantity. The engine produces PL (a raw quantity); the metric computes VPA from it. See naming convention below.
4. **Never name a metric after a raw quantity** — `metrics/pl.py` is WRONG. PL is a raw quantity (engine). The metric computes a ratio from PL. Use the per-share quantity name: `metrics/vpa.py` (VPA = PL/shares).
5. **Never compute TTM/PL for each day individually** — TTM changes quarterly, PL changes quarterly, shares change annually. Use `*_periods()` to get the step function, then do O(1) lookups per day.
6. **Never forget `parse_escala`** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Always apply `parse_escala(r["escala"])` before using values.
7. **Never return a ratio when the denominator <= 0** — P/L with negative earnings, P/VPA with negative equity, Payout with negative earnings, ROE/ROA/ROIC with negative earnings/equity/EBIT, Gross/Operating Margin with negative gross_profit/EBIT/revenue. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
8. **Never hardcode empresa_ids** — DFP and ITR have independent autoincrement IDs. Always call `resolve_company()` separately for each database.
9. **Never create `.bak` files** — forbidden by project rules.
10. **Never rewrite entire files** — surgical edits only.
11. **Never print to stdout** — MCP stdio corruption.
12. **Never put auto-discovery code in `engines/__init__.py` or `metrics/__init__.py`** — auto-discovery is in the CENTRAL `_registry.py` (top level). The `__init__.py` files in `engines/` and `metrics/` are minimal docstrings.
13. **Never edit `engines/__init__.py` or `metrics/__init__.py` to add an engine/metric to a manual inventory list** — there is NO manual inventory. The registry (`list_engines()` / `list_metrics()`) is the source of truth. Adding a file + `register_*()` is all you need. Editing `__init__.py` for inventory defeats the purpose of auto-discovery.
14. **Never import metric modules at the top of `historical.py`** — use the registry (`resolve_metric()`). The registry handles lazy resolution.
15. **Never manually edit `__init__.py` to add a `<metric>_history` mode** — the MANIFEST auto-generates from the registry. Adding a metric = drop a file + `register_metric()`.
16. **Never manually edit `adapters/historical.py` to add a chart adapter** — chart adapters auto-register from the registry. The `historical_<metric>_chart` adapter appears automatically (dual-axis if `per_share_label` is set, single-dataset if `None`).
17. **Never put non-metric files in `metrics/`** — auto-discovery imports everything (except `__init__.py`). Utility modules will break the registry. The `_registry.py` is at the TOP level, not in `metrics/`.
18. **Never put non-engine files in `engines/`** — auto-discovery imports everything (except `__init__.py`). Utility modules will be imported as engines.
19. **Never make `MetricSpec` or `EngineSpec` frozen** — tests need to monkeypatch `spec.history_fn` / `spec.at_fn`. Use `@dataclass` (not `@dataclass(frozen=True)`).
20. **Never mock the module function in tests** — `_metric_history()` calls `spec.history_fn` (captured at registration time). Mock the registry spec: `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`.
21. **Never re-run auto-discovery** — `_auto_discover()` is idempotent (uses a `_done` flag). Don't call it manually; it runs once at import time.
22. **Never forget to mock `cash_at` in ROIC tests** (v1.9 lesson) — ROIC composes 5 engines including `cash`. If you only mock `ebit + tax + pl + debt` and leave `cash_at` to call the real DB, the test breaks (or, if the metric uses `try/except`, ROIC silently falls back to v1.8 behavior and you're not testing the v1.9 cash subtraction). Mock ALL 5 engines in any ROIC test that exercises the cash-subtraction path.
23. **Never use description-based search in metrics** — the `da` engine searches the DFC by `descricao LIKE '%deprec%' OR '%amort%'` because D&A has no fixed CVM code. This pattern stays in ENGINES only. Metrics compose engines via their `at_fn`/`periods_fn` and should never re-query raw CVM data with description filters. If you need a new description-searched quantity, add an ENGINE for it.

---

## ✅ ALWAYS DO

1. **Always resolve empresa_ids separately for DFP and ITR** — They are separate SQLite files with independent autoincrement IDs. Using DFP's IDs to query ITR returns wrong/empty rows.
2. **Always use step-function optimization** — Precompute TTM/PL/shares/cash/debt/EBIT/D&A periods, then lookup per day. Don't recompute for 1200 days.
3. **Always add `data_freshness`** — Use `add_freshness(result)` from `_freshness.py`.
4. **Always run `compileall` before `pytest`** — catches syntax errors early.
5. **Always follow the engine contract** — `<quantity>_at(company, date) -> float | None` + `<quantity>_periods(company) -> list[dict]` + `register_engine(EngineSpec(...))` at module level. Every engine must have all three.
6. **Always follow the metric contract** — For per-share+ratio metrics: `<name>_at` (per-share) + `<ratio>_at` (ratio) + `<name>_history` + `register_metric(MetricSpec(...))`. For fundamental ratios: `<ratio>_at` + `<name>_history` + `register_metric(MetricSpec(..., per_share_*=None))`. Every metric must have `history_fn` + `ratio_fn` + `register_metric`.
7. **Always call `register_engine()` / `register_metric()` at module level** — so the engine/metric auto-registers when the module is imported by auto-discovery.
8. **Always include aliases (Portuguese + English)** — `["pe", "pl", "p/l"]` for lpa, `["dy", "dividend_yield", "yld", "payout"]` for dpa, `["return_on_equity", "retorno_pl", "retorno_patrimonio"]` for roe. Users expect to call `summary(metric="retorno_pl")`, not just `summary(metric="roe")`.
9. **Always set `category` when registering an engine** — one of `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc`, or `other`. The default is `"other"` but should be overridden for every real engine. `list_engines(category="dre")` relies on this for backtest discovery.
10. **Always produce BOTH per-share value and ratio (for Type 1 metrics)** — LPA + P/L, VPA + P/VPA, DPA + Div Yield, RPS + PSR, EBITDA/Ação + EV/EBITDA. The per-share value is useful on its own (backtests). The ratio tells you if the stock is cheap. Bonus ratios (e.g., Payout) are optional. (Fundamental-ratio metrics skip per-share entirely — see Metric Types below.)
11. **Always mock the registry spec in tests** — `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Not the module function.
12. **Always update the adapter count test** when adding a new adapter — `tests/tools/report/test_report_adapters.py` `test_adapters_registered` hardcodes the count.
13. **Always mock ALL engines a metric composes** (v1.9 lesson) — not just some. If a metric calls `cash_at` (like ROIC does), mock it too — even if the metric has a `try/except` wrapper. Otherwise you're either hitting the real DB in tests, OR silently testing the fallback path instead of the v1.9 behavior. The `engines=[...]` field on MetricSpec is your checklist.
14. **Always use `try/except` when calling engines from another metric** (v1.9 lesson with ROIC + cash) — if a metric calls an engine that wasn't originally part of its composition (and might not be mocked in older tests), wrap the call in `try/except Exception:` and fall back to the prior behavior. Example: ROIC calls `cash_at` inside `try/except`, falling back to `PL + Debt` (v1.8) when cash is unavailable. This keeps existing tests passing when you ADD an engine to a metric.
15. **Always update CHANGELOG.md** when adding metrics/engines/modes — see `docs/DOCUMENTATION_GUIDE.md`.
16. **Always use `sorted()` in auto-discovery glob** — `sorted((base / "engines").glob("*.py"))` for deterministic import order across filesystems.
17. **Always import from the central `_registry.py`** — `from skills.cvm.historical._registry import MetricSpec, register_metric`. NOT from `metrics._registry` (old v1.2 location, deleted in v1.3).
18. **Always set `per_share_label=None` for fundamental ratios** — and `per_share_key=None`, `per_share_fn=None`. The chart adapter + summary adapter inspect `per_share_label`: if `None`, single-dataset chart + skip per-share KPI/row.

---

## 📐 Naming Convention

| Layer | File name | Based on | Example |
|-------|-----------|----------|---------|
| Engine | `<quantity>.py` | The raw quantity it produces | `price.py`, `earnings.py`, `shares.py`, `pl.py`, `da.py`, `debt.py`, `cash.py` |
| Metric | `<per_share>.py` (Type 1) OR `<ratio_snake_case>.py` (Type 2) | The per-share quantity (Type 1) OR the ratio name (Type 2) | `lpa.py` (LPA = earnings/shares), `rps.py` (RPS = revenue/shares), `ev_ebitda.py` (EV/EBITDA), `roe.py`, `roic.py`, `gross_margin.py` |

**Rule:** Engine file names are nouns (the raw quantity). Per-share+ratio metric file names are per-share quantity names. Fundamental-ratio metric file names are the ratio name in snake_case. Never mix them — `engines/vpa.py` or `metrics/pl.py` are both WRONG.

**JSON keys in series entries:**
- Per-share value (Type 1 only): metric name (`lpa`, `vpa`, `dpa`, `rps`, `ebitda_ps`)
- Ratio: traditional abbreviation (`pe` for P/L, `pvpa` for P/VPA, `dy` for Div Yield, `psr`, `ev_ebitda`, `roe`, `roa`, `roic`, `gross_margin`, `operating_margin`)
- Engine quantities: `price`, `ttm_earnings`, `shares`, `pl`, `ttm_rev`, `ttm_gp`, `ttm_ebit`, `ttm_tax`, `ttm_da`, `assets`, `cash`, `debt`

---

## 📐 Metric Types

This skill recognizes **three metric types** (Type 3 not yet used):

### Type 1 — Per-share value + price ratio (+ optional bonus ratios)
- **Examples:** lpa (LPA + P/L), vpa (VPA + P/VPA), dpa (DPA + Div Yield + Payout), rps (RPS + PSR), ev_ebitda (EBITDA/Ação + EV/EBITDA)
- **MetricSpec:** all `per_share_*` fields set; `ratio_*` fields set
- **`<name>_history()`:** daily series with per-share + ratio + bonus ratios (uses daily price as the date driver)
- **Chart adapter:** dual-axis (per-share on left axis, ratio on right axis)
- **Summary adapter:** shows both per-share KPI/row AND ratio KPI/row
- **Engines:** always includes `price` + at least one other engine

### Type 2 — Fundamental ratio
- **Examples:** roe (ROE = earnings/PL), roa (ROA = earnings/assets), roic (ROIC = NOPAT/(PL+Debt−Cash)), gross_margin (Lucro Bruto/Receita), operating_margin (EBIT/Receita)
- **MetricSpec:** `per_share_label=None`, `per_share_key=None`, `per_share_fn=None`; only `ratio_*` fields set
- **`<name>_history()`:** series based on the UNION of engine period dates (~4-8 points/year — no daily price driver)
- **Chart adapter:** single-dataset (ratio on one axis)
- **Summary adapter:** shows only the ratio KPI/row (skips per-share)
- **Engines:** does NOT include `price` or `shares` — pure fundamental ratios

### Type 3 — Per-share only (FUTURE, not yet used)
- **MetricSpec:** `ratio_*` fields would be `None`; `per_share_*` fields set
- **Use case:** a per-share value with no natural price ratio (e.g., a custom per-share quantity)
- **Chart adapter:** would produce a single-dataset chart of the per-share value
- The `MetricSpec` already supports this shape — no metrics use it yet.

---

## 📐 Dependency Graph Rule

```
historical.py  (orchestrator — reads from registry, knows both layers)
       │
       ├── _registry.py  (CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories)
       │       │
       │       ├── engines/ (13 engines — LEAVES, never import each other or metrics)
       │       │     ├── market: price.py, dividends.py
       │       │     ├── shares: shares.py
       │       │     ├── dre:    earnings.py, revenue.py, gross_profit.py, ebit.py, tax.py
       │       │     ├── bpa:    assets.py, cash.py
       │       │     ├── bpp:    pl.py, debt.py
       │       │     └── dfc:    da.py
       │       │
       │       └── metrics/ (10 metrics — compose engines, never point at other metrics)
       │             ├── lpa.py             → price + earnings + shares                       (Type 1)
       │             ├── vpa.py             → price + pl + shares                              (Type 1)
       │             ├── dpa.py             → price + dividends + earnings + shares           (Type 1, +payout)
       │             ├── rps.py             → price + revenue + shares                        (Type 1)
       │             ├── ev_ebitda.py       → price + shares + debt + cash + ebit + da        (Type 1, 6 engines)
       │             ├── roe.py             → earnings + pl                                    (Type 2)
       │             ├── roa.py             → earnings + assets                                (Type 2)
       │             ├── roic.py            → ebit + tax + pl + debt + cash                    (Type 2, 5 engines)
       │             ├── gross_margin.py    → gross_profit + revenue                           (Type 2)
       │             └── operating_margin.py → ebit + revenue                                 (Type 2)
       │
       └── (engines never point upward — they're leaves)
```

**Acyclic. Always points downward.** If you find yourself wanting an engine to import a metric, or a metric to import another metric, stop — you're creating coupling. Refactor instead.

**Exception (v1.9 — ROIC + cash):** ROIC imports the cash engine *lazily inside a function body* with `try/except Exception:` so tests that don't mock `cash_at` still pass. This is the ONLY metric→engine lazy import; all other metrics import their engines at module top. The pattern is reserved for metrics that ADD an engine to an existing composition (like ROIC adding cash in v1.9). Document it clearly in the metric's docstring.

---

## 📐 Auto-Discovery Rules

1. **`_registry.py` (top level)** — the CENTRAL auto-discovery module (this is rule #1). Globs `engines/*.py` AND `metrics/*.py` (excluding `__init__.py`). Imports each via `importlib.import_module()`. This triggers `register_engine()` and `register_metric()` calls. Idempotent (uses `_done` flag). Also holds `list_engines(category=...)`, `list_metrics()`, `list_all_metric_names()`, `list_engine_categories()`, `resolve_metric()`.
2. **`engines/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory). Auto-discovery is in the central `_registry.py`.
3. **`metrics/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory). Auto-discovery is in the central `_registry.py`.
4. **`adapters/historical.py`** — iterates over `METRICS` dict and auto-registers chart adapters via `ADAPTERS[f"historical_{name}_chart"] = _adapter_fn`. Adapter inspects `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
5. **`__init__.py`** (skill manifest) — `_build_metric_modes()` iterates over `METRICS` and generates `<metric>_history` mode entries for the MANIFEST.
6. **`historical.py`** — `_make_metric_history_fn()` generates `<metric>_history` functions and assigns them to `globals()`. Handles both Type 1 and Type 2 metrics via `spec.per_share_key` None-check.

**Adding a metric = 1 file in `metrics/` + `register_metric()`.** Everything else auto-generates.
**Adding an engine = 1 file in `engines/` + `register_engine()`.** It's immediately available for metrics to import.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.9 — ROIC tests broke when cash_at wasn't mocked
> - **What happened:** ROIC was updated in v1.9 to subtract cash from invested capital (`IC = PL + Debt - Cash`). This added `cash_at` to ROIC's composition (now 5 engines). Existing ROIC tests from v1.8 only mocked `ebit + tax + pl + debt` — they didn't mock `cash_at`. The new ROIC code called `cash_at(company, date)` which tried to hit the real DFP/ITR DB and either crashed or returned wrong values.
> - **Why it matters:** Adding an engine to an existing metric's composition breaks every test that doesn't mock the new engine. Without protection, you'd have to update every test the moment you touch the metric.
> - **Fix:** Wrap the `cash_at` call in `try/except Exception:` and fall back to `PL + Debt` (v1.8 behavior) when cash is unavailable. This makes ROIC robust when cash data is missing OR not mocked. BUT: tests that exercise the v1.9 cash-subtraction path MUST mock all 5 engines — otherwise they're silently testing the fallback. Documented in INSTRUCTIONS rules #22 (NEVER) + #13/#14 (ALWAYS).

### v1.7 — Fundamental ratios needed None per-share fields
> - **What happened:** When ROE was added (the first fundamental ratio), the existing `MetricSpec` required `per_share_label`, `per_share_key`, `per_share_fn` as positional fields. ROE has no per-share value — it's just `earnings/PL`. Forcing ROE to set dummy per-share values would have broken the chart adapter (dual-axis with a non-existent per-share) and summary adapter (per-share KPI/row with no value).
> - **Why it matters:** The MetricSpec shape has to support BOTH metric types cleanly, not just the original per-share+ratio type.
> - **Fix:** Made `per_share_label`, `per_share_key`, `per_share_fn` optional (`None` default). The chart adapter + summary adapter inspect `per_share_label`: if `None`, single-dataset chart + skip per-share KPI/row. ROE, ROA, ROIC, Gross Margin, Operating Margin all use this pattern.

### v1.4.1 — Manual inventory in __init__.py defeated auto-discovery
> - **What happened:** A contributor added a new engine but also edited `engines/__init__.py` to add the engine to a manual inventory docstring list. Later, when the engine was renamed, the docstring list went stale while the registry stayed correct — contributors got confused about which was the source of truth.
> - **Why it matters:** Two sources of truth (manual inventory + registry) drift over time. The registry auto-discovers everything; the manual list is redundant and error-prone.
> - **Fix:** Removed the manual inventory from `engines/__init__.py` and `metrics/__init__.py`. Both files are now minimal docstrings pointing to the registry: `list_engines()` / `list_metrics()` are the source of truth. Documented in INSTRUCTIONS rules #12 + #13 (NEVER) + the pattern template.

### v1.3 — Registry scattered across subfolders
> - **What happened:** In v1.2, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.
> - **Why it matters:** The pattern wasn't consistent. `list_engines()` didn't exist, so the backtest skill couldn't discover engines programmatically. Adding an engine required editing metrics that needed it, with no central inventory.
> - **Fix:** Moved `_registry.py` to the skill top level (`skills/cvm/historical/_registry.py`). It now handles BOTH engines and metrics auto-discovery. New `EngineSpec` dataclass + `register_engine()`. Both layers self-register. `list_engines()` enables backtest discovery. `engines/__init__.py` and `metrics/__init__.py` simplified to minimal docstrings.

### v1.2 — Frozen MetricSpec broke tests
> - **What happened:** `MetricSpec` was `@dataclass(frozen=True)`. Tests tried to `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)` to mock the history function. Frozen dataclasses raise `FrozenInstanceError` on setattr.
> - **Why it matters:** `_metric_history()` calls `spec.history_fn` (captured at registration time). If we can't patch the spec, we can't mock the history function in tests. Patching the module function (`metrics.lpa.lpa_history`) doesn't work because the spec already holds a reference to the original.
> - **Fix:** Changed `MetricSpec` to `@dataclass` (not frozen). Tests now patch `METRICS["lpa"].history_fn` directly. Documented in INSTRUCTIONS rules #19 + #20.

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
> - **Fix:** `ttm_earnings_at()` handles all 4 cases with explicit branches. Tests cover each path. The same algorithm is reused by `revenue_at`, `gross_profit_at`, `ebit_at`, `tax_at`, and `da_at` (each with their own CVM code/description).

---

## 📐 Pattern Template Checklist (when copying to a new skill)

If you're creating a new skill that follows this pattern:

- [ ] `_registry.py` (top level) — `EngineSpec` (with `category`) + `MetricSpec` (with optional `per_share_*`) + `register_engine` + `register_metric` + auto-discovery (globs both `engines/` and `metrics/`) + `resolve_metric` + `list_engines(category=...)` + `list_metrics()` + aliases
- [ ] `engines/__init__.py` — minimal docstring (NO auto-discovery code, NO manual inventory list)
- [ ] `engines/<quantity>.py` — one per raw quantity, follows engine contract + `register_engine(EngineSpec(..., category="..."))` at module level
- [ ] `metrics/__init__.py` — minimal docstring (NO auto-discovery code, NO manual inventory list)
- [ ] `metrics/<name>.py` — one per metric, calls `register_metric(MetricSpec(...))` at module level. Use `per_share_*=None` for fundamental ratios. Include Portuguese + English aliases.
- [ ] `<skill>.py` — `_metric_history()` reads from registry, auto-generates `<metric>_history` functions. Handle BOTH Type 1 and Type 2 metrics via `spec.per_share_key` None-check.
- [ ] `__init__.py` (skill manifest) — MANIFEST modes auto-generate from registry
- [ ] `adapters/<skill>.py` — chart adapters auto-register from registry. Inspect `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
- [ ] Tests mock the registry spec (not the module function): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Mock ALL engines a metric composes (or use `try/except` if the metric supports missing engines).
- [ ] Docs document the central registry + engine/metric separation + auto-discovery + categories + metric types (Type 1 per-share+ratio, Type 2 fundamental, Type 3 future per-share only)

---

*Last updated: v1.9. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history.*
