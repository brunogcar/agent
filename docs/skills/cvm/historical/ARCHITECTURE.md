<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🏗️ Architecture

**This skill is a thin wrapper over the shared `calculations/` package.** Engines, metrics, and the central `_registry.py` live in `skills/cvm/calculations/` (extracted in v2.2 Phase 1 refactor). Historical adds **mode dispatch** (`<metric>_history`, `summary`, `ratio_history`) + **percentile analysis** on top of the shared engines/metrics.

For the engine/metric library architecture, see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md). This doc covers only the historical-specific layer.

**Current scope (v1.2):** Engines + metrics live in `calculations/` (see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md)). Historical exposes 40 modes total: 37 auto-generated `<metric>_history` (one per metric in calculations) + 3 explicit (`ratio_history`, `summary`, `dashboard`).

## 🔗 Source Code Reference

**[v1.13]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base.py` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

Historical is a thin wrapper — modularized in v1.2 into `_registry.py` + `modes/` + `helpers.py` + `report.py`. The engine/metric library lives in `calculations/`.

| File | Purpose |
|---|---|
| `skills/_base.py` | [v1.13] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/cvm/historical/__init__.py` | [v1.13] Uses `auto_discover_modes()` + `make_route()` from `skills/_base.py` — ~50 lines. MANIFEST + route — modes auto-generated from the metric registry (imported from calculations) |
| `skills/cvm/historical/_registry.py` | [v1.13] Delegates to `skills/_base.py` — creates skill's own MODES dict via `make_registry()`. ~16 lines + `_auto_register_metric_history_modes()` PRESERVED (auto-registers `<metric>_history` modes from calculations `METRICS` — historical-only logic, not in `_base.py`). |
| `skills/cvm/historical/helpers.py` | Historical-specific helpers (date windowing, freshness wrapping, metric-aware summary rendering) extracted from the old monolithic `historical.py` |
| `skills/cvm/historical/report.py` | Skill-level report helpers (consumed by adapters) |
| `skills/cvm/historical/modes/ratio_history.py` | `mode="ratio_history"` — generic dispatch via `resolve_metric()` |
| `skills/cvm/historical/modes/summary.py` | `mode="summary"` — percentile analysis (cheap/fair/expensive) over N-month window |
| `skills/cvm/historical/modes/dashboard.py` | `mode="dashboard"` (v1.2) — multi-tab dashboard payload for the report tool |
| `tools/report_ops/adapters/historical.py` | Auto-registered `historical_<metric>_chart` chart adapters + `historical_summary` table adapter |
| `tools/report_ops/adapters/historical_dashboard.py` | `historical_dashboard` adapter (v1.2 — 71st adapter) |

**Engine/metric library (in calculations/):**

| File | Purpose |
|---|---|
| `skills/cvm/calculations/_registry.py` | **Central registry** — `EngineSpec` + `MetricSpec` + auto-discovery for both `engines/` and `metrics/` + `list_engines(category=...)` + `list_metrics()` + `resolve_metric()`. See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for full design. |
| `skills/cvm/calculations/engines/*.py` | 18 engines (price, dividends, shares, earnings, revenue, gross_profit, ebit, tax, assets, total_assets, cash, pl, debt, current_liabilities, da, capex, operating_cf, investing_cf). See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-source-code-reference) for the full list. |
| `skills/cvm/calculations/metrics/*.py` | 21 metrics (8 per-share+ratio + 13 fundamental). See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-source-code-reference) for the full list. |
| `tools/report_ops/adapters/historical.py` | Auto-registered chart adapters + metric-aware summary adapter. Dual-axis for per-share+ratio metrics, single-dataset for fundamental ratios. Imports `METRICS` + `resolve_metric` from `skills.cvm.calculations._registry`. |

---

## 🧱 Historical vs Calculations — The Wrapper Relationship

`historical/` is a **thin wrapper** over `calculations/`. It adds **mode dispatch** + **percentile analysis** on top of the shared calculations engines/metrics.

### What historical owns (the thin wrapper layer)
- **MANIFEST + `route()`** in `__init__.py` — auto-generates `<metric>_history` modes from `METRICS`.
- **`_metric_history()`** in `historical.py` — wraps each metric's `history_fn` with date windowing + freshness + ratio_count.
- **`_make_metric_history_fn()`** in `historical.py` — factory that generates `<metric>_history` functions into `globals()`.
- **`ratio_history()`** in `historical.py` — generic dispatch via `resolve_metric()`.
- **`summary()`** in `historical.py` — current vs 1Y/3Y/5Y average + min/max/percentile + interpretation. **Percentile analysis is historical-specific** — it lives here, not in calculations.
- **`adapters/historical.py`** (in `tools/report_ops/adapters/`) — auto-registered chart adapters + metric-aware summary adapter.

### What historical does NOT own (delegated to calculations/)
- Engines (18) — all in `calculations/engines/`
- Metrics (21) — all in `calculations/metrics/`
- Registry (`_registry.py`, `EngineSpec`, `MetricSpec`, `register_*`, `resolve_metric`, `list_*`) — in `calculations/_registry.py`
- TTM algorithm, snapshot algorithm, description-based search, multi-code sum, step-function optimization — all in calculations engines/metrics

### Import pattern

```python
# historical/__init__.py + historical.py — top-level imports
from skills.cvm.calculations._registry import METRICS, ENGINES, resolve_metric, list_metrics, list_engines

# historical.py — never imports individual engines/metrics at module top.
# All metric resolution goes through the registry:
spec = resolve_metric(metric_name)        # canonical name or alias
series = spec.history_fn(company, from, to)  # delegates to calculations/metrics/<name>.py
```

This means historical stays in sync with calculations automatically — when a metric is added to calculations, historical's MANIFEST + adapter list + `_make_metric_history_fn` loop all auto-pick it up.

---

## 🌳 Module Tree

```text
skills/cvm/historical/                       # THIN WRAPPER — modularized in v1.2
├── __init__.py              # MANIFEST + route — modes auto-generated from calculations registry + skill _registry.py
├── _registry.py             # Skill-level ModeSpec + @register_mode + auto-discovery (modes/*.py)
├── helpers.py               # Historical-specific helpers (date windowing, freshness, summary rendering)
├── report.py                # Skill-level report helpers (consumed by adapters)
└── modes/
    ├── __init__.py
    ├── ratio_history.py     # mode="ratio_history" — generic metric dispatch via resolve_metric()
    ├── summary.py           # mode="summary" — percentile analysis (cheap/fair/expensive)
    └── dashboard.py         # mode="dashboard" (v1.2) — multi-tab dashboard payload

skills/cvm/calculations/                     # SHARED ENGINE/METRIC LIBRARY (unchanged in v1.2)
├── _registry.py             # CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories
├── engines/                 # 37 metrics in calculations/metrics/ — see calculations/ARCHITECTURE.md for full list
│   ├── __init__.py
│   ├── price.py             # market — COTAHIST
│   ├── dividends.py         # market — B3 cash_dividends DPA TTM
│   ├── shares.py            # shares — FRE + investsite fallback
│   ├── earnings.py          # dre — DFP+ITR 3.11 TTM
│   ├── revenue.py           # dre — DFP+ITR 3.01 TTM
│   ├── gross_profit.py      # dre — DFP+ITR 3.03 TTM
│   ├── ebit.py              # dre — DFP+ITR 3.05 TTM
│   ├── tax.py               # dre — DFP+ITR 3.08 TTM
│   ├── assets.py            # bpa — DFP+ITR BPA 1.01 snapshot (Ativo Circulante)
│   ├── total_assets.py      # bpa — DFP+ITR BPA 1 snapshot (Ativo Total)
│   ├── cash.py              # bpa — DFP+ITR BPA 1.01.01 snapshot
│   ├── pl.py                # bpp — DFP+ITR BPP 2.03 snapshot
│   ├── debt.py              # bpp — DFP+ITR BPP 2.01.04+2.02.01 snapshot (multi-code sum)
│   ├── current_liabilities.py # bpp — DFP+ITR BPP 2.01 snapshot
│   ├── da.py                # dfc — DFP+ITR DFC %deprec%/%amort% TTM (description search)
│   └── capex.py             # dfc — DFP+ITR DFC %imobilizado%/%intangivel% TTM (description search)
└── metrics/                 # 37 metrics — see calculations/ARCHITECTURE.md for full list
    ├── __init__.py
    ├── lpa.py               # Type 1: LPA + P/L
    ├── vpa.py               # Type 1: VPA + P/VPA
    ├── dpa.py               # Type 1: DPA + Div Yield + Payout
    ├── rps.py               # Type 1: RPS + PSR
    ├── ev_ebitda.py         # Type 1: EBITDA/Ação + EV/EBITDA (6 engines)
    ├── roe.py               # Type 2: ROE
    ├── roa.py               # Type 2: ROA
    ├── roic.py              # Type 2: ROIC (5 engines)
    └── ...                  # (29 more — see calculations/ARCHITECTURE.md)

tools/report_ops/adapters/
├── historical.py            # Auto-registered chart adapters + metric-aware summary adapter
└── historical_dashboard.py  # historical_dashboard adapter (v1.2 — 71st adapter)
```

---

## 🗂️ Engine Inventory (by category)

The `category` field on `EngineSpec` groups engines by financial statement / data domain. Use `list_engines(category="dre")` to filter. **Engine inventory is owned by calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the canonical table. Reproduced here for convenience:

| Category | Engines | Description |
|---|---|---|
| `market` | price, dividends | B3 market data (COTAHIST daily close, B3 cash_dividends DPA TTM) |
| `shares` | shares | FRE shares outstanding (+ investsite fallback when FRE NULL) |
| `dre` | earnings, revenue, gross_profit, ebit, tax | DRE statement flows (all TTM derivation, by codigo 3.11, 3.01, 3.03, 3.05, 3.08) |
| `bpa` | assets, total_assets, cash | BPA statement balances (snapshots — 1.01 Ativo Circulante, 1 Ativo Total, 1.01.01 Caixa) |
| `bpp` | pl, debt, current_liabilities | BPP statement balances (snapshots — 2.03 PL, 2.01.04+2.02.01 Debt, 2.01 Passivo Circulante) |
| `dfc` | da, capex | DFC statement flows (description-based search — `%deprec%`/`%amort%` for D&A, `%imobilizado%`/`%intangivel%` for CapEx, TTM derivation) |

**Total: 18 engines in 7 categories.** When we reach 20+ engines, calculations may move to subfolders (`engines/dre/`, `engines/bpa/`, etc.) — until then, the `category` field gives organizational clarity without breaking import paths.

---

## 📊 Metric Inventory (by type)

**Metric inventory is owned by calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the canonical table. Reproduced here for convenience:

| Type | Metric | Per-share | Ratio | Bonus | Engines |
|---|---|---|---|---|---|
| Per-share + price ratio | `lpa` | LPA | P/L | — | price + earnings + shares |
| Per-share + price ratio | `vpa` | VPA | P/VPA | — | price + pl + shares |
| Per-share + price ratio | `dpa` | DPA | Div Yield | Payout | price + dividends + earnings + shares |
| Per-share + price ratio | `rps` | RPS | PSR | — | price + revenue + shares |
| Per-share + price ratio | `ev_ebitda` | EBITDA/Ação | EV/EBITDA | — | price + shares + debt + cash + ebit + da (6 engines) |
| Fundamental ratio | `roe` | — | ROE | — | earnings + pl |
| Fundamental ratio | `roa` | — | ROA | — | earnings + assets |
| Fundamental ratio | `roic` | — | ROIC | — | ebit + tax + pl + debt + cash (5 engines, subtracts cash) |
| Fundamental ratio | `gross_margin` | — | Margem Bruta | — | gross_profit + revenue |
| Fundamental ratio | `operating_margin` | — | Margem Operacional | — | ebit + revenue |
| Fundamental ratio | `net_margin` | — | Margem Líquida | — | earnings + revenue |
| Fundamental ratio | `ebitda_margin` | — | Margem EBITDA | — | ebit + da + revenue |
| Fundamental ratio | `debt_equity` | — | Dívida/PL | — | debt + pl |
| Fundamental ratio | `net_debt_ebitda` | — | DL/EBITDA | — | debt + cash + ebit + da |
| Fundamental ratio | `asset_turnover` | — | Giro de Ativos | — | revenue + assets |
| Fundamental ratio | `capex_revenue` | — | CapEx/Receita | — | capex + revenue |
| Fundamental ratio | `current_ratio` | — | Liquidez Corrente | — | assets + current_liabilities |

**Total: 21 metrics — 8 per-share+ratio + 13 fundamental.** All metrics expose Portuguese aliases (e.g., `margem_bruta`, `retorno_pl`, `retorno_ativos`, `retorno_capital_investido`) plus English aliases (`return_on_equity`, etc.) so users can dispatch via either language.

---

## 🤖 Central Auto-Discovery + Registry Design

**The registry is owned by calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the full design. Historical's interaction with the registry is limited to: importing `METRICS`, `ENGINES`, `resolve_metric`, `list_metrics`, `list_engines` from `skills.cvm.calculations._registry`, and using `resolve_metric()` for metric resolution in `ratio_history()` + `summary()`.

### Why a central registry?

Before v1.3 (historical version), the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.

In v1.3, the registry moved to the **top level** (`skills/cvm/historical/_registry.py` at the time) and handles BOTH engines and metrics. In v1.4.1 (historical), the `category` field was added to `EngineSpec` so engines could be grouped + filtered. In v1.7 (historical), `per_share_*` fields on `MetricSpec` became optional, enabling fundamental-ratio metrics. In v1.11 (Phase 1 refactor), the registry + engines + metrics were extracted from `historical/` into the shared `calculations/` package so other CVM skills can reuse them. This gives:
- **Consistent pattern** — both layers self-register via `register_engine()` / `register_metric()`
- **Single source of truth** — one file holds all specs + auto-discovery logic + category metadata
- **Engine discoverability** — `list_engines()` + `list_engines(category=...)` enable docs auto-generation + backtest skill discovery by statement type
- **Metric type flexibility** — fundamental ratios skip per-share fields cleanly via `None`
- **Cleaner `__init__.py` files** — `engines/__init__.py` and `metrics/__init__.py` are minimal docstrings (no auto-discovery code)
- **Cross-skill reuse** — historical, valuation, financials, backtest all import from one calculations package; no duplication

### How it works (in calculations/_registry.py)

```python
# calculations/_registry.py — central auto-discovery

def _auto_discover():
    """Glob both engines/*.py and metrics/*.py, import each via importlib."""
    if getattr(_auto_discover, "_done", False):
        return  # idempotent — avoid re-running on re-import
    _auto_discover._done = True

    base = Path(__file__).parent

    # Discover engines (triggers register_engine calls)
    for py_file in sorted((base / "engines").glob("*.py")):
        if py_file.name != "__init__.py":
            importlib.import_module(f"skills.cvm.calculations.engines.{py_file.stem}")

    # Discover metrics (triggers register_metric calls)
    for py_file in sorted((base / "metrics").glob("*.py")):
        if py_file.name != "__init__.py":
            importlib.import_module(f"skills.cvm.calculations.metrics.{py_file.stem}")

_auto_discover()  # run at import time
```

```python
# calculations/engines/da.py — self-registration at module level (dfc category)
from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="da",
    quantity="ttm_da",
    at_fn=da_at,
    periods_fn=da_periods,
    source="DFP + ITR DFC (Depreciação e Amortização by description search, TTM)",
    category="dfc",
))
```

```python
# calculations/metrics/roic.py — fundamental ratio (per_share_* = None)
from skills.cvm.calculations._registry import MetricSpec, register_metric  # noqa: E402

register_metric(MetricSpec(
    name="roic",
    per_share_label=None,       # None for fundamental ratios
    per_share_key=None,
    per_share_fn=None,
    ratio_label="ROIC",
    ratio_key="roic",
    ratio_fn=roic_at,
    history_fn=roic_history,
    engines=["ebit", "tax", "pl", "debt", "cash"],
    aliases=["return_on_invested_capital", "retorno_capital_investido"],
))
```

### Auto-generation chain (in historical — consumer skill side)

When a new metric is registered **in calculations**, the following auto-generate **in historical** (consumer skill):
1. **`<metric>_history` mode in MANIFEST** — `_build_metric_modes()` in `historical/__init__.py` iterates `METRICS`
2. **`<metric>_history` function in historical.py** — `_make_metric_history_fn()` generates functions via `globals()`
3. **`historical_<metric>_chart` adapter** — `adapters/historical.py` iterates `METRICS` and auto-registers. The adapter inspects `spec.per_share_label`: if `None`, single-dataset chart (fundamental); if set, dual-axis chart (per-share + ratio).
4. **`ratio_history(metric=<name>)` dispatch** — `resolve_metric()` handles canonical + alias names
5. **`summary(metric=<name>)` metric-awareness** — `resolve_metric()` returns the spec, summary reads labels + keys from it (skips per-share KPI/row when `per_share_label` is `None`)

**Adding a metric to calculations = drop a file in `calculations/metrics/` + `register_metric()`.** Zero edits to `historical/__init__.py`, `historical.py`, or `adapters/historical.py`. The new `<metric>_history` mode appears in historical's MANIFEST automatically.

---

## 🔢 Algorithms

**All algorithms (TTM, snapshot, multi-code sum, description-based search, DPA TTM, Payout, ROIC) live in calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for the full algorithm reference. Historical does NOT implement any algorithm — it delegates to `spec.history_fn` for each metric, which in turn calls the calculations engine functions.

### Percentile analysis (historical-specific — owned by historical)

The one algorithm that IS historical-specific is **percentile analysis** in `summary()`:

```
For a metric's daily series over the last N months:
  1. Collect all valid ratio values (skip None entries — e.g., negative earnings years)
  2. Compute current value = ratio at date_to
  3. Compute averages over the last 1Y / 3Y / 5Y windows
  4. Compute min / max over the full window
  5. Compute percentile = (rank of current value in sorted series) / (count of valid values) * 100
  6. Interpretation:
     - ≤ 25th percentile → "cheap (below 25th percentile of history)"
     - 25-75th percentile → "fair (between 25th-75th percentile of history)"
     - ≥ 75th percentile → "expensive (above 75th percentile of history)"
```

This logic lives in `historical.py:summary()` and is the reason historical exists as a separate skill from calculations — percentile analysis is a consumer concern, not a library concern.

---

## 📊 Data Flow (example: ev_ebitda_history — most complex metric)

**The data flow below happens inside calculations/metrics/ev_ebitda.py** — historical just calls `spec.history_fn(company, date_from, date_to)` and wraps the result with freshness + ratio_count. The full flow is documented in [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-data-flow-example-ev_ebitda_history--most-complex-metric). Summary:

```
historical._metric_history(company="PETR4", metric_name="ev_ebitda", months=60)
  │
  ├── resolve_metric("ev_ebitda")  →  MetricSpec  (from calculations._registry)
  │
  ├── date_from = today - 60 months;  date_to = today
  │
  ├── spec.history_fn("PETR4", date_from, date_to)   ← delegates to calculations/metrics/ev_ebitda.py
  │     │
  │     ├── price_series("PETR4", from, to)  → ~1200 daily prices
  │     ├── shares_periods("PETR4")  → FRE step function
  │     ├── debt_periods("PETR4")    → DFP+ITR BPP step function
  │     ├── cash_periods("PETR4")    → DFP+ITR BPA step function
  │     ├── ebit_periods("PETR4")    → DFP+ITR DRE step function
  │     ├── da_periods("PETR4")      → DFP+ITR DFC step function
  │     └── For each daily price: step-function lookups → EBITDA, EBITDA/share, EV, EV/EBITDA
  │
  ├── Wrap result: add status, metric name, labels, total_days, ratio_count, series
  └── add_freshness(result)  →  final response
```

Fundamental metrics (roe, roa, roic, margins, leverage, turnover, liquidity) follow a different shape — no daily price driver, so the series is built from the union of engine period dates (~4-8 points/year) rather than 1200 daily points.

---

## 💡 Key Design Patterns (historical-specific)

1. **Thin wrapper over calculations/** — historical owns mode dispatch + percentile analysis only. All engines, metrics, registry, and algorithms live in calculations. This keeps historical focused on user-facing functionality and lets other CVM skills reuse calculations without coupling to historical.
2. **Auto-generated MANIFEST modes** — `_build_metric_modes()` in `historical/__init__.py` iterates `METRICS` (imported from calculations) and generates one `<metric>_history` mode per metric. Adding a metric to calculations = a new mode appears in historical automatically.
3. **Auto-generated `<metric>_history` functions** — `_make_metric_history_fn()` in `historical.py` generates functions into `globals()` at import time. Each is a thin wrapper around `_metric_history()`.
4. **Auto-registered chart adapters** — `adapters/historical.py` iterates `METRICS` and registers `historical_<metric>_chart` for each. Dual-axis for Type 1 metrics (per-share+ratio), single-dataset for Type 2 (fundamental). The adapter inspects `spec.per_share_label`.
5. **Metric-aware summary** — `summary()` reads `spec.per_share_label`, `spec.per_share_key`, `spec.ratio_label`, `spec.ratio_key` from the registry and renders KPIs/rows conditionally. Skips per-share KPI/row when `per_share_label` is `None` (fundamental ratios).
6. **Lazy metric resolution** — `historical.py` never imports individual metric modules at module top. All metric resolution goes through `resolve_metric()` from the calculations registry. This keeps the import graph clean and avoids coupling.
7. **Percentile analysis is historical-specific** — the percentile computation in `summary()` (rank-based, with cheap/fair/expensive interpretation thresholds at 25th/75th percentiles) lives in historical, not calculations. Other consumer skills may have different summary styles.

For the engine/metric library design patterns (central registry, engine categories, TTM derivation, snapshot, description-based search, multi-code sum, step-function optimization, flexible MetricSpec, PT+EN aliases), see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-key-design-patterns).

---

## ➕ How to Add a New Engine

**Engines live in calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-how-to-add-a-new-engine) for the full guide. Summary:

1. Create a new file in `skills/cvm/calculations/engines/` (e.g., `working_capital.py`).
2. Query your data source directly (DFP/ITR/FRE/COTAHIST/B3). Apply `parse_escala` to raw CVM values.
3. Implement `<quantity>_at(company, date)` and `<quantity>_periods(company)` following the engine contract.
4. Call `register_engine(EngineSpec(...))` at module level with `category` set.
5. Add tests in `tests/skills/cvm/calculations/` (mock the DB connection).
6. **NEVER add engines to `skills/cvm/historical/`** — they belong in `skills/cvm/calculations/`.
7. **NEVER edit `engines/__init__.py`** — there is no manual inventory. The registry is the source of truth.

---

## ➕ How to Add a New Metric

**Metrics live in calculations/** — see [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-how-to-add-a-new-metric) for the full guide. Summary:

1. **Confirm the engines you need already exist** in calculations. If not, add the ENGINE first.
2. Create `skills/cvm/calculations/metrics/<name>.py` with `<name>_at` / `<ratio>_at` / `<name>_history` + `register_metric(MetricSpec(...))`.
3. **That's it for calculations.** The following auto-generate **in historical** (consumer skill):
   - `<name>_history` mode in the historical MANIFEST
   - `<name>_history` function in `historical.py`
   - `historical_<name>_chart` adapter in `adapters/historical.py`
   - `ratio_history(metric=<name>)` dispatch (via `resolve_metric`)
   - `summary(metric=<name>)` metric-awareness (via `resolve_metric`)
4. Add tests in `tests/skills/cvm/calculations/test_<name>.py`:
   - Mock the registry spec's history_fn: `monkeypatch.setattr(METRICS["<name>"], "history_fn", fake_fn)`
   - **Mock ALL engines the metric composes** — not just some.
5. Update `docs/skills/cvm/calculations/` (API.md + CHANGELOG.md) + `docs/skills/cvm/historical/CHANGELOG.md` (consumer-visible new mode).
6. **NEVER add metrics to `skills/cvm/historical/`** — they belong in `skills/cvm/calculations/`.

---

## 🔮 Backtest Foundation

The calculations engines + metrics are designed for reuse by a future `skills/cvm/backtest/` skill:

```python
# Future backtest skill — reuses the same 18 engines + 21 metrics from calculations
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.metrics.lpa import lpa_at, pe_at
from skills.cvm.calculations.metrics.vpa import vpa_at, pvpa_at
from skills.cvm.calculations.metrics.dpa import dpa_at, dy_at, payout_at
from skills.cvm.calculations.metrics.rps import rps_at, psr_at
from skills.cvm.calculations.metrics.ev_ebitda import ebitda_ps_at, ev_ebitda_at
from skills.cvm.calculations.metrics.roe import roe_at
from skills.cvm.calculations.metrics.roa import roa_at
from skills.cvm.calculations.metrics.roic import roic_at
from skills.cvm.calculations.metrics.gross_margin import gross_margin_at
from skills.cvm.calculations.metrics.operating_margin import operating_margin_at
from skills.cvm.calculations.metrics.net_margin import net_margin_at
from skills.cvm.calculations.metrics.debt_equity import debt_equity_at
from skills.cvm.calculations.metrics.net_debt_ebitda import net_debt_ebitda_at
from skills.cvm.calculations.metrics.current_ratio import current_ratio_at

# Per-share+ratio signals: buy when P/L < 5 AND P/VPA < 1.0 AND Div Yield > 5%
if (pe_at("PETR4", "2022-06-30") < 5
    and pvpa_at("PETR4", "2022-06-30") < 1.0
    and dy_at("PETR4", "2022-06-30") > 0.05):
    entry_price = price_at("PETR4", "2022-06-30")
    # ... compute returns

# Fundamental signals: buy when ROIC > 15% AND Operating Margin > 10% AND Net Debt/EBITDA < 3
if (roic_at("PETR4", "2022-06-30") > 0.15
    and operating_margin_at("PETR4", "2022-06-30") > 0.10
    and net_debt_ebitda_at("PETR4", "2022-06-30") < 3):
    ...

# Per-share values directly: strong dividend + cheap on EV/EBITDA
if (dpa_at("PETR4", "2022-06-30") > 1.50
    and ev_ebitda_at("PETR4", "2022-06-30") < 6):
    ...
```

No duplication — the backtest skill reuses the same engines and metrics from calculations. `list_engines(category=...)` enables discovery by statement type (e.g., "give me all DRE flow engines for a custom signal"). Historical is irrelevant to backtest — backtest imports calculations directly.

---

## 📐 Pattern Template Checklist (when copying to a new skill)

The pattern template is now **calculations**, not historical. See [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md#-pattern-template-checklist-when-copying-to-a-new-skill) for the 10-item checklist. Historical is a consumer of calculations, not a template itself.

---

## 🧪 Testing

```bash
# Run all historical tests (mode dispatch + percentile + MANIFEST + route)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/historical/ -v -W error --tb=short

# Run calculations tests (engines + metrics + registry)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/calculations/ -v -W error --tb=short

# Run both together (historical is a consumer of calculations)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/calculations/ tests/skills/cvm/historical/ -v -W error --tb=short
```

**Test architecture:**
- `tests/skills/cvm/conftest.py` — autouse env var fixture (PLANNER_MODEL etc.) so `core.config` loads during collection
- `tests/skills/cvm/calculations/conftest.py` — same env var pattern (safety net for direct calculations test runs)
- Historical tests (`tests/skills/cvm/historical/test_historical.py`) cover mode dispatch, MANIFEST auto-generation, route(), summary percentile logic. They mock the registry spec: `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`.
- Calculations tests (`tests/skills/cvm/calculations/test_*.py`) cover each engine + each metric + the registry. Mock ALL engines a metric composes — or use `try/except` if the metric supports missing engines (ROIC+cash lesson).
- Fundamental ratio tests verify `per_share_key is None` and no `price`/`shares` in series entries.
- Per-share+ratio tests verify dual-dataset yAxisID assertions (in `tests/tools/report/test_report_chart.py`).

**Test file layout:**
```text
tests/skills/cvm/
├── conftest.py                                # Autouse env vars (PLANNER_MODEL etc.)
├── test_integration.py                        # Cross-skill integration
├── calculations/                              # Calculations package tests (11 files)
│   ├── conftest.py                            # Same env var pattern
│   ├── test_registry.py                       # Engine + metric auto-discovery, aliases, categories
│   ├── test_lpa.py                            # LPA + P/L metric
│   ├── test_vpa.py                            # VPA + P/VPA metric + PL engine
│   ├── test_dpa.py                            # DPA + DY + Payout metric + dividends engine
│   ├── test_rps.py                            # RPS + PSR metric + revenue engine
│   ├── test_roe.py                            # ROE fundamental ratio
│   ├── test_roa_margins.py                    # ROA + Gross Margin + Operating Margin
│   ├── test_roic.py                           # ROIC + tax engine + debt engine + cash engine
│   ├── test_ev_ebitda.py                      # EV/EBITDA + cash engine + da engine
│   ├── test_fundamental_ratios.py             # net_margin + ebitda_margin + debt_equity + net_debt_ebitda + asset_turnover
│   └── test_capex_current_ratio.py            # capex_revenue + current_ratio (+ capex + total_assets + current_liabilities engines)
├── historical/
│   └── test_historical.py                     # Historical mode dispatch, MANIFEST, route, summary percentile (consumer skill)
├── comparison/test_comparison.py              # Comparison skill
├── dividends/test_dividends.py                # Dividends skill
├── financials/test_financials.py              # Financials skill
├── governance/test_governance.py              # Governance skill
├── insider/test_insider.py                    # Insider skill
├── screener/test_screener.py                  # Screener skill
├── shareholders/test_shareholders.py          # Shareholders skill
└── valuation/test_valuation.py                # Valuation skill
```

**Bridge test split (historical v1.13):**
`test_bridge.py` (968 lines, 42 tests) was split into 4 files under `tests/data_sources/cvm/bridge/`:
- `conftest.py` — shared fixtures (bridge_db, populated_bridge, dfp_with_bridge)
- `_helpers.py` — mock factories (_mock_dividends_ok, _patch_cad, etc.)
- `test_sync.py` — sync engine + ISIN fallback (13 tests)
- `test_query.py` — query engine lookup/status/resolve (12 tests)
- `test_resolver.py` — _bridge.py resolve_company (9 tests)
- `test_parse_escala.py` — parse_escala helper (8 tests)

---

*Last updated: 2026-08-06 (v1.19 — `skills/_base.py` extraction; `_auto_register_metric_history_modes()` preserved — see CHANGELOG.md). See [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules, [calculations/ARCHITECTURE.md](../calculations/ARCHITECTURE.md) for engine/metric library architecture.*
