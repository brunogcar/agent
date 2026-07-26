<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🏗️ Architecture

This skill is the **pattern template** for central auto-discovery + registry architecture. The central `_registry.py`, engine/metric separation, and self-registration pattern are designed to be copied by other skills that need extensibility.

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/historical/_registry.py` | **Central registry** — EngineSpec + MetricSpec + auto-discovery for both engines/ and metrics/ |
| `skills/cvm/historical/__init__.py` | MANIFEST + route — modes auto-generated from the metric registry |
| `skills/cvm/historical/historical.py` | Main: `_metric_history()`, `ratio_history()`, `summary()`. Auto-generates `<metric>_history` functions from the registry. |
| `skills/cvm/historical/engines/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/historical/engines/price.py` | COTAHIST daily close: `price_at()`, `price_series()` |
| `skills/cvm/historical/engines/earnings.py` | TTM earnings: `ttm_earnings_at()`, `ttm_earnings_periods()`. DFP + ITR. |
| `skills/cvm/historical/engines/shares.py` | FRE shares: `shares_at()`, `shares_periods()` (+ investsite fallback) |
| `skills/cvm/historical/engines/pl.py` | PL snapshot: `pl_at()`, `pl_periods()`. DFP + ITR BPP 2.03. |
| `skills/cvm/historical/engines/dividends.py` | DPA TTM: `dividends_at()`, `dividends_periods()`. B3 cash_dividends. |
| `skills/cvm/historical/metrics/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/historical/metrics/lpa.py` | LPA + P/L metric: `lpa_at()`, `pe_at()`, `lpa_history()`. Engines: price + earnings + shares. |
| `skills/cvm/historical/metrics/vpa.py` | VPA + P/VPA metric: `vpa_at()`, `pvpa_at()`, `vpa_history()`. Engines: price + pl + shares. |
| `skills/cvm/historical/metrics/dpa.py` | DPA + Div Yield + Payout metric: `dpa_at()`, `dy_at()`, `payout_at()`, `dpa_history()`. Engines: price + dividends + earnings + shares. |
| `skills/cvm/historical/metrics/ev_ebitda.py` | EV/EBITDA stub for future |
| `tools/report_ops/adapters/historical.py` | Auto-registered chart adapters + metric-aware summary adapter |

---

## 🧱 Engine vs Metric — The Core Pattern

This skill enforces a strict separation between **engines** (data access) and **metrics** (ratio math). This is the most important architectural rule. Violating it creates coupling that makes future metrics and the backtest skill impossible to reuse cleanly.

### Engines (basics — one per raw quantity)

An engine fetches ONE raw number at any historical date from its data source(s). Engines are **leaves** — they never import each other and never import metrics.

```
engines/
├── price.py      → price_at(ticker, date)          # COTAHIST daily close
├── earnings.py   → ttm_earnings_at(company, date)   # DFP + ITR TTM derivation
├── shares.py     → shares_at(company, date)         # FRE + investsite fallback
├── pl.py         → pl_at(company, date)             # DFP + ITR BPP 2.03 snapshot
└── dividends.py  → dividends_at(ticker, date)       # B3 cash_dividends DPA TTM
```

**Engine contract** (every engine follows this shape):
- `<quantity>_at(company, date) -> float | None` — value at most recent data point <= date
- `<quantity>_periods(company) -> list[dict]` — all data points `[{"date": "...", "<quantity>": value}, ...]` sorted oldest-first (for step-function optimization)
- `register_engine(EngineSpec(...))` at module level — self-registers with the central registry

**EngineSpec dataclass:**
```python
@dataclass
class EngineSpec:
    name: str           # "price", "earnings", "shares", "pl", "dividends"
    quantity: str       # "close", "ttm", "shares", "pl", "dpa" — JSON key in periods
    at_fn: Callable     # price_at, ttm_earnings_at, shares_at, pl_at, dividends_at
    periods_fn: Callable # price_series, ttm_earnings_periods, ...
    source: str         # "COTAHIST (B3 daily OHLCV, 2010+)" — for docs + backtest discovery
```

### Metrics (per-share value + price ratio + optional bonus ratios)

A metric imports 2+ engines and produces BOTH a per-share value AND a price ratio. Metrics **never** query CVM/B3 directly — that's the engine's job.

```
metrics/
├── lpa.py   → LPA (earnings/shares) + P/L (price/LPA)
├── vpa.py   → VPA (pl/shares) + P/VPA (price/vpa)
├── dpa.py   → DPA (dividends TTM) + Div Yield (DPA/price) + Payout (DPA/LPA)  [bonus ratio]
└── ev_ebitda.py  → stub for future
```

**Each metric produces:**
- **Per-share value**: LPA, VPA, DPA — useful on its own (e.g., backtest filters on EPS)
- **Price ratio**: P/L, P/VPA, Div Yield — tells you if the stock is cheap vs history
- **Optional bonus ratios**: Payout (DPA/LPA) — included in the series + summary

**Metric contract:**
- `<name>_at(company, date) -> float | None` — per-share value
- `<ratio>_at(company, date) -> float | None` — price ratio
- `<name>_history(company, date_from, date_to) -> list[dict]` — daily series with per-share + ratio + bonus ratios
- `register_metric(MetricSpec(...))` at module level — self-registers with the central registry

### Dependency graph (MUST stay acyclic)

```
historical.py  (orchestrator — reads from central registry, knows both layers)
       │
       ├── _registry.py  (EngineSpec + MetricSpec + auto-discovery + resolve_metric)
       │       │
       │       ├── engines/price.py      ─┐
       │       ├── engines/earnings.py    │ (leaves — never import each other or metrics)
       │       ├── engines/shares.py      │
       │       ├── engines/pl.py          │
       │       ├── engines/dividends.py  ─┘
       │       │
       │       ├── metrics/lpa.py  ──┬── engines/price.py + earnings.py + shares.py
       │       │                      └── (composes 3 engines, produces LPA + P/L)
       │       ├── metrics/vpa.py  ──┬── engines/price.py + pl.py + shares.py
       │       │                      └── (composes 3 engines, produces VPA + P/VPA)
       │       └── metrics/dpa.py  ──┬── engines/price.py + dividends.py + earnings.py + shares.py
       │                              └── (composes 4 engines, produces DPA + Div Yield + Payout)
       │
       └── (engines never point upward — they're leaves)
```

Engines never point upward. Metrics never point at other metrics. `historical.py` is the only module that knows about both engines and metrics together (via the central registry).

---

## 🌳 Module Tree

```text
skills/cvm/historical/
├── __init__.py              # MANIFEST + route — modes auto-generated from registry
├── _registry.py             # CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric
├── historical.py            # _metric_history(), ratio_history(), summary()
├── engines/
│   ├── __init__.py          # Minimal docstring (auto-discovery is in _registry.py)
│   ├── price.py             # COTAHIST: price_at(), price_series() + register_engine()
│   ├── earnings.py          # DFP + ITR TTM: ttm_earnings_at(), ttm_earnings_periods() + register_engine()
│   ├── shares.py            # FRE + investsite: shares_at(), shares_periods() + register_engine()
│   ├── pl.py                # DFP + ITR BPP 2.03: pl_at(), pl_periods() + register_engine()
│   └── dividends.py         # B3 cash_dividends: dividends_at(), dividends_periods() + register_engine()
└── metrics/
    ├── __init__.py          # Minimal docstring (auto-discovery is in _registry.py)
    ├── lpa.py               # LPA + P/L: lpa_at(), pe_at(), lpa_history() + register_metric()
    ├── vpa.py               # VPA + P/VPA: vpa_at(), pvpa_at(), vpa_history() + register_metric()
    ├── dpa.py               # DPA + Div Yield + Payout: dpa_at(), dy_at(), payout_at(), dpa_history() + register_metric()
    └── ev_ebitda.py         # stub for future
```

---

## 🤖 Central Auto-Discovery + Registry Design

### Why a central registry?

Before v1.3, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.

In v1.3, the registry moved to the **top level** (`skills/cvm/historical/_registry.py`) and handles BOTH engines and metrics. This gives:
- **Consistent pattern** — both layers self-register via `register_engine()` / `register_metric()`
- **Single source of truth** — one file holds all specs + auto-discovery logic
- **Engine discoverability** — `list_engines()` enables docs auto-generation + backtest skill discovery
- **Cleaner `__init__.py` files** — `engines/__init__.py` and `metrics/__init__.py` are minimal docstrings (no auto-discovery code)

### How it works

```python
# _registry.py — central auto-discovery

def _auto_discover():
    """Glob both engines/*.py and metrics/*.py, import each via importlib."""
    if getattr(_auto_discover, "_done", False):
        return  # idempotent — avoid re-running on re-import
    _auto_discover._done = True

    base = Path(__file__).parent

    # Discover engines (triggers register_engine calls)
    for py_file in sorted((base / "engines").glob("*.py")):
        if py_file.name != "__init__.py":
            importlib.import_module(f"skills.cvm.historical.engines.{py_file.stem}")

    # Discover metrics (triggers register_metric calls)
    for py_file in sorted((base / "metrics").glob("*.py")):
        if py_file.name != "__init__.py":
            importlib.import_module(f"skills.cvm.historical.metrics.{py_file.stem}")

_auto_discover()  # run at import time
```

```python
# engines/price.py — self-registration at module level
from skills.cvm.historical._registry import EngineSpec, register_engine

register_engine(EngineSpec(
    name="price",
    quantity="close",
    at_fn=price_at,
    periods_fn=price_series,
    source="COTAHIST (B3 daily OHLCV, 2010+)",
))
```

```python
# metrics/dpa.py — self-registration at module level
from skills.cvm.historical._registry import MetricSpec, register_metric

register_metric(MetricSpec(
    name="dpa",
    per_share_label="DPA", per_share_key="dpa", per_share_fn=dpa_at,
    ratio_label="Div Yield", ratio_key="dy", ratio_fn=dy_at,
    history_fn=dpa_history,
    engines=["price", "dividends", "earnings", "shares"],
    aliases=["dy", "dividend_yield", "yld", "payout"],
))
```

### Auto-generation chain

When a new metric is registered, the following auto-generate:
1. **`<metric>_history` mode in MANIFEST** — `_build_metric_modes()` in `__init__.py` iterates `METRICS`
2. **`<metric>_history` function in historical.py** — `_make_metric_history_fn()` generates functions via `globals()`
3. **`historical_<metric>_chart` adapter** — `adapters/historical.py` iterates `METRICS` and auto-registers
4. **`ratio_history(metric=<name>)` dispatch** — `resolve_metric()` handles canonical + alias names
5. **`summary(metric=<name>)` metric-awareness** — `resolve_metric()` returns the spec, summary reads labels + keys from it

**Adding a metric = drop a file in metrics/ + `register_metric()`.** Zero edits to `__init__.py`, `historical.py`, or `adapters/historical.py`.

---

## 🔢 Algorithms

### TTM Earnings (earnings.py)

Derives trailing twelve months earnings at any date.

```
For date D, find the most recent ITR period (data_fim_exerc <= D):

  ITR current period (e.g., Q2 2024, meses=6) = cumulative H1 2024 earnings
  ITR prior year same period (Q2 2023, meses=6) = cumulative H1 2023 earnings
  DFP prior year (2023, meses=12) = full year 2023 earnings

  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1
       = (full year 2023) - (H1 2023) + (H1 2024)
       = 12 months ending 2024-06-30
```

### PL Snapshot (pl.py)

PL is a **snapshot** (point-in-time balance), not a flow. Simpler than earnings — no TTM derivation. Just find the most recent BPP snapshot with `data_fim_exerc <= date`.

```
For date D:
  1. Query DFP BPP codigo 2.03 (meses=12) → annual snapshots at Dec 31
  2. Query ITR BPP codigo 2.03 (meses=3/6/9) → quarterly snapshots at Mar/Jun/Sep 30
  3. Merge all snapshots, find most recent with data_fim_exerc <= D
  4. Return that value
```

### DPA TTM (dividends.py)

DPA = trailing 12-month dividends per share. The B3 `cash_dividends.rate` field is already per-share (R$/share), so we just sum rates in the 365-day window.

```
For date D:
  DPA_TTM = SUM(cash_dividends.rate WHERE payment_date BETWEEN D-365 AND D)

JCP (Juros sobre Capital Próprio) is included — it's a real cash distribution.
The label field distinguishes Dividendo vs JCP, but we sum both.
```

**Special cases:**
- No payment dates at all → return `None` (no data available)
- All payment dates after query date → return `None` (can't compute TTM)
- Company exists but paid nothing in the window → return `0.0` (different from `None`)

### Payout (dpa.py)

Payout = DPA / LPA = dividends per share / earnings per share.

```
For date D:
  DPA   = dividends_at(ticker, D)      # TTM dividends per share
  LPA   = ttm_earnings_at(ticker, D) / shares_at(ticker, D)  # TTM earnings per share
  Payout = DPA / LPA
```

**Returns None when:** DPA is None (no dividends data), LPA <= 0 (negative earnings — payout meaningless), or shares missing.

---

## 📊 Data Flow (example: dpa_history)

```
dpa_history("PETR4", "2020-01-01", "2024-12-31")
  │
  ├── price_series("PETR4", "2020-01-01", "2024-12-31")
  │     → COTAHIST: ~1200 daily close prices
  │
  ├── dividends_at("PETR4", date) per day
  │     → B3 cash_dividends: SUM(rate WHERE payment_date in [date-365, date])
  │     → Recomputed per day (single SQL query per day — dividends are discrete events)
  │
  ├── ttm_earnings_periods("PETR4")
  │     → DFP + ITR: step function [{date, ttm}, ...]
  │
  ├── shares_periods("PETR4")
  │     → FRE: step function [{date, shares}, ...]
  │
  └── For each daily price:
        find most recent TTM (step function lookup)
        find most recent shares (step function lookup)
        LPA = TTM / shares
        DY = DPA / price
        Payout = DPA / LPA
        → [{date, price, dpa, dy, payout, ttm_earnings, shares, lpa}, ...]
```

---

## 💡 Key Design Decisions

- **Central registry at top level** — `_registry.py` lives at `skills/cvm/historical/`, not inside `engines/` or `metrics/`. This lets it auto-discover BOTH subfolders. Modeled after `tools/report_ops/_registry.py`.
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`. Consistent pattern. `list_engines()` enables backtest discovery.
- **Engines are standalone** — imported independently by any skill (e.g., future backtest). No coupling to `historical.py` or to each other.
- **Metrics compose engines** — `lpa.py` imports `price + earnings + shares`. `dpa.py` imports `price + dividends + earnings + shares` (4 engines). New metrics import different engine combinations.
- **Each metric produces per-share + ratio (+ optional bonus)** — DPA (per-share) + Div Yield (ratio) + Payout (bonus). All exposed in the series + summary.
- **Step function optimization** — TTM earnings change ~4x per year, PL ~4x per year, shares ~1x per year, dividends on payment dates. Precompute step functions, do O(1) lookups per day. (Exception: DPA TTM is a rolling 365-day window, recomputed per day via a single SQL query.)
- **parse_escala applied** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Engines apply `parse_escala` to convert to BRL.
- **Negative earnings/equity → None ratio** — When TTM earnings <= 0 (P/L, Payout) or PL <= 0 (P/VPA), the ratio is meaningless. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
- **0.0 vs None for DPA** — 0.0 means "company exists but pays no dividends" (valid, yield = 0). None means "no dividends data available" (can't compute). The dividends engine distinguishes these.
- **Auto-generated MANIFEST modes** — `<metric>_history` modes appear in the MANIFEST automatically when a metric is registered. No manual editing.
- **Auto-registered chart adapters** — `historical_<metric>_chart` adapters auto-register. Each produces a dual-dataset chart (per-share value + ratio).
- **Lazy metric imports** — `historical.py` resolves metrics via the registry (`resolve_metric()`), not at module top. This keeps the import graph clean.

---

## ➕ How to Add a New Engine

1. Create a new file in `engines/` (e.g., `revenue.py`).
2. Query your data source directly (DFP/ITR/FRE/COTAHIST/B3). Apply `parse_escala` to raw CVM values. Use `connect_dfp` / `connect_itr` / `connect_fre` from `data_sources/cvm/_db.py`, or `data_sources.b3.dividends.catalog.connect` for B3 dividends. Resolve tickers via `data_sources.cvm._bridge.resolve_company()`.
3. Implement `<quantity>_at(company, date)` and `<quantity>_periods(company)` following the engine contract.
4. Call `register_engine(EngineSpec(...))` at module level.
5. Add an entry to the engine inventory in `engines/__init__.py` docstring.
6. Add tests in `tests/skills/cvm/historical/` (mock the DB connection).
7. **NEVER import a metric from an engine.** Engines are below metrics in the dependency graph.

---

## ➕ How to Add a New Metric

1. **Confirm the engines you need already exist.** If not, add the ENGINE first.
2. Create `metrics/<name>.py` with:
   - `<name>_at(company, date)` → per-share value
   - `<ratio>_at(company, date)` → price ratio
   - Optional: `<bonus>_at(company, date)` → bonus ratio (e.g., `payout_at`)
   - `<name>_history(company, date_from, date_to)` → daily series with per-share + ratio + bonus ratios
3. Call `register_metric(MetricSpec(...))` at module level.
4. **That's it.** The following auto-generate:
   - `<name>_history` mode in the MANIFEST
   - `<name>_history` function in `historical.py`
   - `historical_<name>_chart` adapter in `adapters/historical.py`
   - `ratio_history(metric=<name>)` dispatch (via `resolve_metric`)
   - `summary(metric=<name>)` metric-awareness (via `resolve_metric`)
5. Add tests in `tests/skills/cvm/historical/test_<name>.py` (mock the engines via the registry: `monkeypatch.setattr(METRICS["<name>"], "history_fn", fake_fn)`).
6. Update `docs/skills/cvm/historical/` (API.md + CHANGELOG.md).

---

## 🔮 Backtest Foundation

The engines are designed for reuse by a future `skills/cvm/backtest/` skill:

```python
# Future backtest skill
from skills.cvm.historical.engines.price import price_at
from skills.cvm.historical.metrics.lpa import lpa_at, pe_at
from skills.cvm.historical.metrics.vpa import vpa_at, pvpa_at
from skills.cvm.historical.metrics.dpa import dpa_at, dy_at, payout_at

# Signal: buy when P/L < 5 AND P/VPA < 1.0 AND Div Yield > 5%
if (pe_at("PETR4", "2022-06-30") < 5
    and pvpa_at("PETR4", "2022-06-30") < 1.0
    and dy_at("PETR4", "2022-06-30") > 0.05):
    entry_price = price_at("PETR4", "2022-06-30")
    # ... compute returns

# Or use per-share values directly
if dpa_at("PETR4", "2022-06-30") > 1.50:  # strong dividend per share
    ...
```

No duplication — the backtest skill reuses the same engines and metrics.

---

*Last updated: 2026-07-26 (v1.3 — central registry + engine self-registration + DPA metric). See [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
