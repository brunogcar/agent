<- Back to [CVM Skills](HISTORICAL.md)

# 📐 CALCULATIONS — Shared Engine + Metric Library

The shared calculations layer between raw `data_sources/` (CVM DFP/ITR/FRE, B3 COTAHIST/dividends) and the user-facing CVM skills (historical, valuation, financials, backtest). Contains **16 engines** (one per raw financial quantity) and **17 metrics** (per-share values + price ratios + fundamental ratios), all auto-discovered via a central registry.

**Key characteristics:**
- **Engine vs Metric separation** — Engines (`engines/`) are leaves that fetch ONE raw quantity each. Metrics (`metrics/`) compose 2+ engines into a ratio. Engines never import each other or metrics; the dependency graph is strictly acyclic.
- **Central auto-discovery** — A single `_registry.py` at the top level globs both `engines/*.py` and `metrics/*.py` and imports them via `importlib`. Adding an engine/metric = drop a file + `register_*()`. No manual inventory lists anywhere.
- **6 engine categories** — `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc`. `list_engines(category=...)` filters engines by financial statement domain (useful for the future backtest skill).
- **2 metric types** — Per-share + price ratio (5: lpa, vpa, dpa, rps, ev_ebitda — produces both a per-share value and a price ratio, dual-axis chart) and fundamental ratio (12: roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin, debt_equity, net_debt_ebitda, asset_turnover, capex_revenue, current_ratio — pure engine ratio, single-dataset chart).
- **PT + EN aliases on every metric** — Users can dispatch via `summary(metric="retorno_pl")` or `summary(metric="roe")` interchangeably. `resolve_metric()` handles canonical names + aliases.
- **Pattern template** — The central `_registry.py` + engine/metric folder structure is designed to be copied by any skill that needs extensibility. See [INSTRUCTIONS.md](calculations/INSTRUCTIONS.md) for the pattern template checklist.

---

## 🚀 Quick Start

```python
# Direct engine import — fetch ONE raw quantity at a historical date
from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.da import da_at, da_periods
from skills.cvm.calculations.engines.debt import debt_at, debt_periods

# Direct metric import — compose engines into a ratio
from skills.cvm.calculations.metrics.lpa import lpa_at, pe_at, lpa_history
from skills.cvm.calculations.metrics.roe import roe_at, roe_history
from skills.cvm.calculations.metrics.ev_ebitda import ev_ebitda_at, ebitda_ps_at
from skills.cvm.calculations.metrics.roic import roic_at

# Registry API — discover engines/metrics, resolve aliases
from skills.cvm.calculations._registry import (
    list_engines, list_metrics, list_engine_categories,
    list_all_metric_names, resolve_metric, ENGINES, METRICS,
)

# Discover engines by financial statement
for name in list_engines(category="dre"):
    spec = ENGINES[name]
    print(f"{name}: {spec.source}")

# Resolve a metric by canonical name or alias
spec = resolve_metric("retorno_pl")  # → METRICS["roe"]
print(f"{spec.name}: {spec.ratio_label} engines={spec.engines}")
```

---

## ⚙️ Configuration

No skill-specific `.env` variables. The calculations layer requires the following data sources to be synced (each engine fails gracefully — returns `None` — if its data source is missing):

| Data source | Used by engines | Sync status |
|---|---|---|
| `data_sources/b3/cotahist` | `price` (daily OHLCV, 2010+) | Required for all price-ratio metrics |
| `data_sources/b3/dividends` | `dividends` (cash dividends per ticker) | Required for `dpa` metric |
| `data_sources/cvm/dfp` | All `dre`/`bpa`/`bpp` engines (annual, 2010+) | Required for TTM + snapshot engines |
| `data_sources/cvm/itr` | All `dre`/`bpa`/`bpp` engines (quarterly cumulative, 2011+) | Required for TTM derivation (TTM computable from ~2012+) |
| `data_sources/cvm/fre` | `shares` (shares outstanding) | Optional — investsite.com.br fallback used when FRE NULL |
| `data_sources/cvm/bridge` | All engines (ticker → CNPJ resolution) | Required — without it, no company can be resolved |
| `data_sources/cvm/dfc` | `da`, `capex` (description-based DFC search) | Required for EV/EBITDA, EBITDA margin, net_debt_ebitda, capex_revenue |

---

## 🔀 When to Use (for other CVM skills)

| Caller | What to import | Why |
|---|---|---|
| `skills/cvm/historical/` | Engines + metrics + registry | Time-series modes (`<metric>_history`), `summary`, `ratio_history` — already integrated in Phase 1 |
| `skills/cvm/valuation/` (Phase 2) | Engines + metrics directly | Per-share intrinsic-value models (Graham, Gordon, FCF) — needs `lpa_at`, `vpa_at`, `dpa_at`, `rps_at`, `ebitda_ps_at` |
| `skills/cvm/financials/` (Phase 3) | Engines directly | Current financial snapshot tables — needs `*_at()` functions for each statement line |
| `skills/cvm/backtest/` (Phase 4) | Engines + metrics + `list_engines(category=...)` | Strategy backtests — needs `*_at()` for entry signals + `*_periods()` for step-function optimization |
| Any custom analysis | Engines directly | Engines are standalone — importable by any skill without coupling to the registry |

**Importing engines directly is supported and encouraged.** The engine contract (`*_at()` + `*_periods()` + `register_engine()`) is stable. The registry is only required for auto-discovery, alias resolution, and category filtering.

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](calculations/ARCHITECTURE.md) | Source code reference, module/test trees, engine/metric pattern, central auto-discovery design, key design patterns, algorithms (TTM, snapshot, description-search, multi-code sum), data flow (ev_ebitda), how-to guides, testing |
| [API.md](calculations/API.md) | All 16 engine function signatures + 17 metric function signatures + registry API (EngineSpec, MetricSpec, register/resolve/list functions) + error handling |
| [CHANGELOG.md](calculations/CHANGELOG.md) | Version history — v1.0 extraction from historical v2.1, breaking changes, deferred items |
| [INSTRUCTIONS.md](calculations/INSTRUCTIONS.md) | AI editing rules — NEVER DO (13), ALWAYS DO (8), naming convention, dependency graph rule, anti-patterns (v1.2–v1.9 lessons), pattern template checklist |

---

*Last updated: 2026-07-26 (v1.0). See subfiles for detailed documentation.*
