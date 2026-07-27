<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🏗️ Architecture

The historical skill is the **first consumer** of the shared calculations library. It orchestrates engines + metrics (via the calculations registry) to produce time-series modes, generic ratio history, and metric-aware summaries with percentile analysis.

**This skill no longer contains engines or metrics** — they were extracted to `skills/cvm/calculations/` in v2.2 (Phase 1 refactor). The historical skill now contains only:
- `__init__.py` — MANIFEST + route (modes auto-generated from the calculations metric registry)
- `historical.py` — `_metric_history()`, `ratio_history()`, `summary()` (mode dispatch + percentile analysis + summary interpretation)

**For engine + metric architecture, design patterns, algorithms, and how-to guides**, see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md). The historical skill docs cover only skill-specific concerns (mode dispatch, MANIFEST auto-generation, percentile analysis, summary interpretation, testing).

---

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/historical/__init__.py` | MANIFEST + route — modes auto-generated from the calculations metric registry via `_build_metric_modes()` + `_build_manifest()`. |
| `skills/cvm/historical/historical.py` | Main: `_metric_history()` (shared implementation behind every `<metric>_history` mode), `_make_metric_history_fn()` (factory that generates `<metric>_history` functions into `globals()`), `ratio_history()` (generic dispatch via `resolve_metric()`), `summary()` (metric-aware current + 1Y/3Y/5Y averages + percentile + interpretation). Handles BOTH per-share+ratio and fundamental-ratio metrics via `spec.per_share_key` None-check. |
| `tools/report_ops/adapters/historical.py` | Auto-registered chart adapters + metric-aware summary adapter. Dual-axis for per-share+ratio metrics, single-dataset for fundamental ratios. Iterates `METRICS` from the calculations registry. |
| `skills/cvm/calculations/_registry.py` | **Central registry** (calculations library) — EngineSpec + MetricSpec + auto-discovery + `resolve_metric()` + `list_engines(category=...)` + `list_metrics()`. Imported by `__init__.py` and `historical.py`. See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md). |
| `skills/cvm/calculations/engines/*.py` | 16 engine modules. See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the full engine inventory. |
| `skills/cvm/calculations/metrics/*.py` | 17 metric modules. See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the full metric inventory. |

---

## 🌳 Module Tree

```text
skills/cvm/historical/
├── __init__.py              # MANIFEST + route — modes auto-generated from calculations registry
└── historical.py            # _metric_history(), ratio_history(), summary() — skill-specific orchestration

(skills/cvm/calculations/ — shared engine + metric library, see ../calculations/ARCHITECTURE.md)
```

---

## 🔀 Mode Dispatch Flow

The historical skill has THREE categories of modes, all driven by the calculations metric registry:

### 1. Auto-generated `<metric>_history` modes

When the calculations registry loads (at import time of `skills.cvm.calculations._registry`), every registered metric becomes a `<metric>_history` mode in the MANIFEST. The flow:

```
1. import skills.cvm.historical → triggers _build_manifest() in __init__.py
2. _build_metric_modes() iterates list_metrics() from calculations._registry
3. For each metric, generates a MANIFEST entry:
   - description (from spec.per_share_label + spec.ratio_label + spec.engines)
   - params: {company: str, months: int=60}
   - examples (one skill() call example)
4. _build_manifest() also adds the 2 generic modes (ratio_history, summary)
5. MANIFEST["modes"] = {<metric>_history for each metric} + {ratio_history, summary}

When route(mode="<metric>_history", params=...) is called:
1. Validate mode is in MANIFEST["modes"]
2. Build dispatch dict from list_metrics(): dispatch[f"{name}_history"] = getattr(historical, f"{name}_history")
3. Filter params by inspect.signature(fn).parameters
4. Call fn(**filtered) → _metric_history(company, metric_name, months)
5. _metric_history resolves spec via resolve_metric(metric_name), calls spec.history_fn(company, date_from, date_to)
6. Wraps result with status, metric, per_share_label, ratio_label, date_from, date_to, total_days, <ratio_key>_days, series
7. Adds data_freshness via add_freshness()
```

**Adding a metric = drop a file in `skills/cvm/calculations/metrics/` + `register_metric()`.** The `<metric>_history` mode auto-appears in the historical MANIFEST. Zero edits to `historical/__init__.py`, `historical/historical.py`, or `adapters/historical.py`.

### 2. `ratio_history` (generic, alias-aware)

```python
def ratio_history(company: str = "", metric: str = "lpa", months: int = 60) -> dict:
    # 1. Resolve alias → canonical via resolve_metric(metric)
    # 2. If unknown metric: return {"status": "error", "error": "Unknown metric '...'. Available: [...]}
    # 3. Call _metric_history(company, spec.name, months)
```

Accepts canonical names (`lpa`, `vpa`, `roe`) AND aliases (`pe`, `pl`, `p/l`, `retorno_pl`). Same return shape as `<metric>_history` modes.

### 3. `summary` (generic, metric-aware, with percentile + interpretation)

```python
def summary(company: str = "", metric: str = "lpa", months: int = 60) -> dict:
    # 1. Resolve alias → canonical via resolve_metric(metric)
    # 2. Get max(months, 60) months of history (percentile needs ≥ 5Y)
    # 3. Extract ratio values (filter None and <= 0)
    # 4. Compute current_ratio + 1Y/3Y/5Y averages + min/max + percentile
    # 5. Generate interpretation: "cheap" / "fair" / "expensive" based on percentile
    # 6. Build current block with per_share + ratio + engine components
    # 7. Return {status, metric, per_share_label, ratio_label, current, averages, range, percentile, interpretation, ...}
```

**Metric-aware:** the `current` block includes per-share value + ratio when `spec.per_share_label` is set (Type 1), and only the ratio when `per_share_label is None` (Type 2 fundamental). See [API.md](API.md) for the full return schema.

---

## 📊 Percentile Analysis + Summary Interpretation

The `summary` mode computes a percentile rank of the current ratio value against the 5-year history, then maps it to a human-readable interpretation:

| Percentile | Interpretation | Meaning |
|---|---|---|
| ≤ 25 | `cheap (below 25th percentile of history)` | Stock is cheaper than 75% of its 5Y history |
| 25–75 | `fair (between 25th-75th percentile of history)` | Stock is in the middle of its 5Y range |
| ≥ 75 | `expensive (above 75th percentile of history)` | Stock is more expensive than 75% of its 5Y history |

**Algorithm:**
```
1. Get ratio_values = [s[ratio_key] for s in series if s[ratio_key] is not None and s[ratio_key] > 0]
   (filter None — missing data — AND <= 0 — negative earnings/equity make ratio meaningless)
2. current_ratio = ratio_values[-1]  (most recent valid value)
3. percentile = 100 * count(ratio_values <= current_ratio) / len(ratio_values)
4. averages = {
     "1y": avg(ratio_values within last 365 days),
     "3y": avg(ratio_values within last 1095 days),
     "5y": avg(ratio_values within last 1825 days),
   }
5. range = {"min": min(ratio_values), "max": max(ratio_values)}
6. interpretation = "cheap" / "fair" / "expensive" based on percentile
```

**Error cases:**
- No series (no price data) → `{"status": "not_found", "error": "No price data for '<company>'"}`
- No valid ratio data (all negative earnings/equity in window) → `{"status": "not_found", "error": "No valid <label> data for '<company>' (possibly negative earnings/equity)"}`

---

## 📊 Report Adapters (auto-registered)

Chart adapters are auto-registered for each metric from the calculations registry. The summary adapter is metric-aware.

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_<metric>_chart` (one per metric) | `<metric>_history` | **Dual-dataset** line chart (per-share + ratio, dual Y axis) when `spec.per_share_label` is set; **single-dataset** line chart (ratio on one axis) when `None` |
| `historical_summary` | `summary` | KPI strip + summary table. Metric-aware: renders per-share KPI/row when `spec.per_share_label` is set; skips it when `None` |

Adapters auto-register by iterating `METRICS` from the calculations registry. **Adding a metric = `historical_<metric>_chart` auto-appears.** Zero edits to `adapters/historical.py`.

---

## 🧪 Testing

```bash
# Run all historical skill tests (mode dispatch, MANIFEST, route — engines/metrics in calculations/)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/historical/ -v -W error --tb=short

# Run all CVM skill tests (calculations + historical + comparison + dividends + ...)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/ -v -W error --tb=short
```

**Test architecture:**
- `tests/skills/cvm/conftest.py` — autouse env var fixture (`PLANNER_MODEL=test` etc.) so `core.config` loads during collection
- Historical skill tests now contain only `test_historical.py` (mode dispatch, MANIFEST, route) — engine/metric tests moved to `tests/skills/cvm/calculations/` in v2.2
- `test_historical.py` mocks the registry spec (not module functions): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`
- Mock ALL engines a metric composes — or rely on the `try/except` wrapper in metrics like ROIC (v1.9 lesson; see [calculations/INSTRUCTIONS.md](../calculations/INSTRUCTIONS.md) anti-patterns)
- Fundamental ratio tests verify `per_share_key is None` and no `price`/`shares` in series entries
- Per-share+ratio tests verify dual-dataset yAxisID assertions

**Test file layout:**
```text
tests/skills/cvm/
├── conftest.py                           # Autouse env vars (PLANNER_MODEL etc.)
├── test_integration.py                   # Cross-skill integration
├── calculations/                         # ← calculations library tests (see ../calculations/ARCHITECTURE.md)
│   ├── conftest.py
│   ├── test_engines.py
│   ├── test_registry.py
│   └── test_<metric>.py (one per metric)
├── historical/                           # ← historical skill tests (mode dispatch only)
│   └── test_historical.py                # Modes (lpa_history, ratio_history, summary), MANIFEST, route
├── comparison/test_comparison.py         # Comparison skill
├── dividends/test_dividends.py           # Dividends skill
├── financials/test_financials.py         # Financials skill
├── governance/test_governance.py         # Governance skill
├── insider/test_insider.py               # Insider skill
├── screener/test_screener.py             # Screener skill
├── shareholders/test_shareholders.py     # Shareholders skill
└── valuation/test_valuation.py           # Valuation skill
```

**v2.2 test split:** Engine/metric tests moved from `tests/skills/cvm/historical/test_<metric>.py` to `tests/skills/cvm/calculations/test_<metric>.py`. Historical skill tests slimmed to `test_historical.py` only. See [calculations/CHANGELOG.md](../calculations/CHANGELOG.md) for the v1.0 calculations entry that documents this split.

---

*Last updated: 2026-07-26 (v2.2). See [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules. Engine + metric architecture: [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md).*
