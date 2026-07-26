<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🏗️ Architecture

This skill is the **pattern template** for central auto-discovery + registry architecture. The central `_registry.py`, engine/metric separation, and self-registration pattern are designed to be copied by other skills that need extensibility.

**Current scope (v1.9):** 13 engines in 6 categories (market, shares, dre, bpa, bpp, dfc) + 10 metrics in 2 types (per-share+ratio and fundamental ratio).

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/historical/_registry.py` | **Central registry** — EngineSpec + MetricSpec + auto-discovery for both engines/ and metrics/ + `list_engines(category=...)` + `list_metrics()` + `resolve_metric()` |
| `skills/cvm/historical/__init__.py` | MANIFEST + route — modes auto-generated from the metric registry |
| `skills/cvm/historical/historical.py` | Main: `_metric_history()`, `ratio_history()`, `summary()`. Auto-generates `<metric>_history` functions from the registry. Handles BOTH per-share+ratio and fundamental-ratio metrics via `per_share_key` check. |
| `skills/cvm/historical/engines/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/historical/engines/price.py` | **market** — COTAHIST daily close: `price_at()`, `price_series()` |
| `skills/cvm/historical/engines/dividends.py` | **market** — B3 cash_dividends DPA TTM: `dividends_at()`, `dividends_periods()` |
| `skills/cvm/historical/engines/shares.py` | **shares** — FRE shares (+ investsite fallback): `shares_at()`, `shares_periods()` |
| `skills/cvm/historical/engines/earnings.py` | **dre** — TTM earnings (DFP+ITR codigo 3.11): `ttm_earnings_at()`, `ttm_earnings_periods()` |
| `skills/cvm/historical/engines/revenue.py` | **dre** — TTM net revenue (codigo 3.01): `revenue_at()`, `revenue_periods()` |
| `skills/cvm/historical/engines/gross_profit.py` | **dre** — TTM gross profit (codigo 3.03): `gross_profit_at()`, `gross_profit_periods()` |
| `skills/cvm/historical/engines/ebit.py` | **dre** — TTM EBIT (codigo 3.05): `ebit_at()`, `ebit_periods()` |
| `skills/cvm/historical/engines/tax.py` | **dre** — TTM IR+CSLL (codigo 3.08, typically negative): `tax_at()`, `tax_periods()` |
| `skills/cvm/historical/engines/assets.py` | **bpa** — Ativo Total snapshot (codigo 1.01): `assets_at()`, `assets_periods()` |
| `skills/cvm/historical/engines/cash.py` | **bpa** — Caixa e Equivalentes snapshot (codigo 1.01.01): `cash_at()`, `cash_periods()` |
| `skills/cvm/historical/engines/pl.py` | **bpp** — PL snapshot (codigo 2.03): `pl_at()`, `pl_periods()` |
| `skills/cvm/historical/engines/debt.py` | **bpp** — Debt snapshot (sum of codigos 2.01.04 + 2.02.01): `debt_at()`, `debt_periods()` |
| `skills/cvm/historical/engines/da.py` | **dfc** — TTM D&A via description-based search (`%deprec%` OR `%amort%`): `da_at()`, `da_periods()` |
| `skills/cvm/historical/metrics/__init__.py` | Minimal docstring (auto-discovery is in `_registry.py`) |
| `skills/cvm/historical/metrics/lpa.py` | **Per-share+ratio** — LPA + P/L: `lpa_at()`, `pe_at()`, `lpa_history()`. Engines: price + earnings + shares. |
| `skills/cvm/historical/metrics/vpa.py` | **Per-share+ratio** — VPA + P/VPA: `vpa_at()`, `pvpa_at()`, `vpa_history()`. Engines: price + pl + shares. |
| `skills/cvm/historical/metrics/dpa.py` | **Per-share+ratio** — DPA + Div Yield + Payout (bonus): `dpa_at()`, `dy_at()`, `payout_at()`, `dpa_history()`. Engines: price + dividends + earnings + shares. |
| `skills/cvm/historical/metrics/rps.py` | **Per-share+ratio** — RPS + PSR: `rps_at()`, `psr_at()`, `rps_history()`. Engines: price + revenue + shares. |
| `skills/cvm/historical/metrics/ev_ebitda.py` | **Per-share+ratio** — EBITDA/Ação + EV/EBITDA: `ebitda_ps_at()`, `ev_ebitda_at()`, `ev_ebitda_history()`. Engines: price + shares + debt + cash + ebit + da (most complex — 6 engines). |
| `skills/cvm/historical/metrics/roe.py` | **Fundamental ratio** — ROE = earnings/PL: `roe_at()`, `roe_history()`. Engines: earnings + pl. No price, no shares. |
| `skills/cvm/historical/metrics/roa.py` | **Fundamental ratio** — ROA = earnings/assets: `roa_at()`, `roa_history()`. Engines: earnings + assets. |
| `skills/cvm/historical/metrics/roic.py` | **Fundamental ratio** — ROIC = NOPAT / (PL + Debt − Cash) (v1.9 subtracts cash): `roic_at()`, `roic_history()`. Engines: ebit + tax + pl + debt + cash. |
| `skills/cvm/historical/metrics/gross_margin.py` | **Fundamental ratio** — Margem Bruta = gross_profit/revenue: `gross_margin_at()`, `gross_margin_history()`. Engines: gross_profit + revenue. |
| `skills/cvm/historical/metrics/operating_margin.py` | **Fundamental ratio** — Margem Operacional = EBIT/revenue: `operating_margin_at()`, `operating_margin_history()`. Engines: ebit + revenue. |
| `tools/report_ops/adapters/historical.py` | Auto-registered chart adapters + metric-aware summary adapter. Dual-axis for per-share+ratio metrics, single-dataset for fundamental ratios. |

---

## 🧱 Engine vs Metric — The Core Pattern

This skill enforces a strict separation between **engines** (data access) and **metrics** (ratio math). This is the most important architectural rule. Violating it creates coupling that makes future metrics and the backtest skill impossible to reuse cleanly.

### Engines (basics — one per raw quantity)

An engine fetches ONE raw number at any historical date from its data source(s). Engines are **leaves** — they never import each other and never import metrics.

```
engines/
├── price.py         → price_at(ticker, date)              # COTAHIST daily close
├── dividends.py     → dividends_at(ticker, date)          # B3 cash_dividends DPA TTM
├── shares.py        → shares_at(company, date)            # FRE + investsite fallback
├── earnings.py      → ttm_earnings_at(company, date)      # DFP+ITR 3.11 TTM derivation
├── revenue.py       → revenue_at(company, date)           # DFP+ITR 3.01 TTM derivation
├── gross_profit.py  → gross_profit_at(company, date)      # DFP+ITR 3.03 TTM derivation
├── ebit.py          → ebit_at(company, date)              # DFP+ITR 3.05 TTM derivation
├── tax.py           → tax_at(company, date)               # DFP+ITR 3.08 TTM (typically negative)
├── assets.py        → assets_at(company, date)            # DFP+ITR BPA 1.01 snapshot
├── cash.py          → cash_at(company, date)              # DFP+ITR BPA 1.01.01 snapshot
├── pl.py            → pl_at(company, date)                # DFP+ITR BPP 2.03 snapshot
├── debt.py          → debt_at(company, date)              # DFP+ITR BPP 2.01.04+2.02.01 snapshot (multi-code sum)
└── da.py            → da_at(company, date)                # DFP+ITR DFC %deprec%/%amort% TTM (description search)
```

**Engine contract** (every engine follows this shape):
- `<quantity>_at(company, date) -> float | None` — value at most recent data point <= date
- `<quantity>_periods(company) -> list[dict]` — all data points `[{"date": "...", "<quantity>": value}, ...]` sorted oldest-first (for step-function optimization)
- `register_engine(EngineSpec(...))` at module level — self-registers with the central registry

**EngineSpec dataclass:**
```python
@dataclass
class EngineSpec:
    name: str           # "price", "earnings", "shares", "pl", "da", ...
    quantity: str       # "close", "ttm", "shares", "pl", "ttm_da", ... — JSON key in periods
    at_fn: Callable     # price_at, ttm_earnings_at, shares_at, pl_at, da_at, ...
    periods_fn: Callable # price_series, ttm_earnings_periods, da_periods, ...
    source: str         # "COTAHIST (B3 daily OHLCV, 2010+)" — for docs + backtest discovery
    category: str = "other"  # "market" | "shares" | "dre" | "bpa" | "bpp" | "dfc" | "other"
```

### Metrics (per-share value + price ratio, OR fundamental ratio)

A metric imports 2+ engines and produces either:

**Type 1 — Per-share value + price ratio (+ optional bonus ratios):**
- Per-share value: LPA, VPA, DPA, RPS, EBITDA/Ação — useful on its own (e.g., backtest filters on EPS)
- Price ratio: P/L, P/VPA, Div Yield, PSR, EV/EBITDA — tells you if the stock is cheap vs history
- Optional bonus ratios: Payout (DPA/LPA) — included in the series + summary
- Chart adapter produces a **dual-axis chart** (per-share on left axis, ratio on right axis)

**Type 2 — Fundamental ratio:**
- A pure ratio of two engine values, no price, no shares (e.g., ROE = earnings/PL)
- `per_share_label`, `per_share_key`, `per_share_fn` are all `None` in MetricSpec
- Chart adapter produces a **single-dataset chart** (ratio on one axis)

**Type 3 — Per-share only (FUTURE, not yet used):** a per-share value without a price ratio. `ratio_*` fields would be `None`. The MetricSpec already supports this shape — no metrics use it yet.

```
metrics/
├── lpa.py               # Per-share+ratio: LPA (earnings/shares) + P/L (price/LPA)
├── vpa.py               # Per-share+ratio: VPA (pl/shares) + P/VPA (price/vpa)
├── dpa.py               # Per-share+ratio: DPA + Div Yield + Payout (bonus)
├── rps.py               # Per-share+ratio: RPS (revenue/shares) + PSR (price/RPS)
├── ev_ebitda.py         # Per-share+ratio: EBITDA/Ação + EV/EBITDA (6 engines, most complex)
├── roe.py               # Fundamental: ROE = earnings / PL
├── roa.py               # Fundamental: ROA = earnings / assets
├── roic.py              # Fundamental: ROIC = NOPAT / (PL + Debt - Cash)
├── gross_margin.py      # Fundamental: Margem Bruta = gross_profit / revenue
└── operating_margin.py  # Fundamental: Margem Operacional = EBIT / revenue
```

**Metric contract:**
- `<name>_at(company, date) -> float | None` — per-share value (None for fundamental ratios)
- `<ratio>_at(company, date) -> float | None` — ratio (P/L, ROE, EV/EBITDA, ...)
- Optional: `<bonus>_at(company, date)` — bonus ratio (e.g., `payout_at`)
- `<name>_history(company, date_from, date_to) -> list[dict]` — daily series with per-share + ratio + bonus ratios (per-share+ratio metrics) OR ratio + engine values (fundamental metrics)
- `register_metric(MetricSpec(...))` at module level — self-registers with the central registry

### Dependency graph (MUST stay acyclic)

```
historical.py  (orchestrator — reads from central registry, knows both layers)
       │
       ├── _registry.py  (EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories)
       │       │
       │       ├── engines/price.py         ─┐
       │       ├── engines/dividends.py       │
       │       ├── engines/shares.py          │ (leaves — never import each other or metrics)
       │       ├── engines/earnings.py        │
       │       ├── engines/revenue.py         │
       │       ├── engines/gross_profit.py    │
       │       ├── engines/ebit.py            │
       │       ├── engines/tax.py             │
       │       ├── engines/assets.py          │
       │       ├── engines/cash.py            │
       │       ├── engines/pl.py              │
       │       ├── engines/debt.py            │
       │       └── engines/da.py            ─┘
       │       │
       │       ├── metrics/lpa.py             ──┬── price + earnings + shares              (per-share+ratio)
       │       ├── metrics/vpa.py               ├── price + pl + shares                     (per-share+ratio)
       │       ├── metrics/dpa.py               ├── price + dividends + earnings + shares   (per-share+ratio, +payout)
       │       ├── metrics/rps.py               ├── price + revenue + shares                (per-share+ratio)
       │       ├── metrics/ev_ebitda.py         ├── price + shares + debt + cash + ebit + da (per-share+ratio, 6 engines)
       │       ├── metrics/roe.py               ├── earnings + pl                           (fundamental)
       │       ├── metrics/roa.py               ├── earnings + assets                       (fundamental)
       │       ├── metrics/roic.py              ├── ebit + tax + pl + debt + cash           (fundamental, 5 engines)
       │       ├── metrics/gross_margin.py      ├── gross_profit + revenue                  (fundamental)
       │       └── metrics/operating_margin.py──┘ ebit + revenue                           (fundamental)
       │
       └── (engines never point upward — they're leaves)
```

Engines never point upward. Metrics never point at other metrics. `historical.py` is the only module that knows about both engines and metrics together (via the central registry).

**Exception (v1.9 — ROIC):** ROIC imports the cash engine *lazily inside a function body* with `try/except` so tests that don't mock `cash_at` still pass. This is the only metric→engine lazy import; all other metrics import their engines at module top. See INSTRUCTIONS.md anti-patterns for the v1.9 lesson.

---

## 🌳 Module Tree

```text
skills/cvm/historical/
├── __init__.py              # MANIFEST + route — modes auto-generated from registry
├── _registry.py             # CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories
├── historical.py            # _metric_history(), ratio_history(), summary() — handles BOTH metric types
├── engines/
│   ├── __init__.py          # Minimal docstring (auto-discovery is in _registry.py)
│   ├── price.py             # market — COTAHIST: price_at(), price_series() + register_engine(category="market")
│   ├── dividends.py         # market — B3 cash_dividends: dividends_at(), dividends_periods() + register_engine(category="market")
│   ├── shares.py            # shares — FRE + investsite: shares_at(), shares_periods() + register_engine(category="shares")
│   ├── earnings.py          # dre — DFP+ITR 3.11 TTM: ttm_earnings_at(), ttm_earnings_periods() + register_engine(category="dre")
│   ├── revenue.py           # dre — DFP+ITR 3.01 TTM: revenue_at(), revenue_periods() + register_engine(category="dre")
│   ├── gross_profit.py      # dre — DFP+ITR 3.03 TTM: gross_profit_at(), gross_profit_periods() + register_engine(category="dre")
│   ├── ebit.py              # dre — DFP+ITR 3.05 TTM: ebit_at(), ebit_periods() + register_engine(category="dre")
│   ├── tax.py               # dre — DFP+ITR 3.08 TTM: tax_at(), tax_periods() + register_engine(category="dre")
│   ├── assets.py            # bpa — DFP+ITR BPA 1.01 snapshot: assets_at(), assets_periods() + register_engine(category="bpa")
│   ├── cash.py              # bpa — DFP+ITR BPA 1.01.01 snapshot: cash_at(), cash_periods() + register_engine(category="bpa")
│   ├── pl.py                # bpp — DFP+ITR BPP 2.03 snapshot: pl_at(), pl_periods() + register_engine(category="bpp")
│   ├── debt.py              # bpp — DFP+ITR BPP 2.01.04+2.02.01 snapshot (multi-code sum): debt_at(), debt_periods() + register_engine(category="bpp")
│   └── da.py                # dfc — DFP+ITR DFC %deprec%/%amort% TTM (description search): da_at(), da_periods() + register_engine(category="dfc")
└── metrics/
    ├── __init__.py          # Minimal docstring (auto-discovery is in _registry.py)
    ├── lpa.py               # Per-share+ratio: lpa_at(), pe_at(), lpa_history() + register_metric()
    ├── vpa.py               # Per-share+ratio: vpa_at(), pvpa_at(), vpa_history() + register_metric()
    ├── dpa.py               # Per-share+ratio: dpa_at(), dy_at(), payout_at(), dpa_history() + register_metric()
    ├── rps.py               # Per-share+ratio: rps_at(), psr_at(), rps_history() + register_metric()
    ├── ev_ebitda.py         # Per-share+ratio: ebitda_ps_at(), ev_ebitda_at(), ev_ebitda_history() + register_metric()
    ├── roe.py               # Fundamental: roe_at(), roe_history() + register_metric(per_share_*=None)
    ├── roa.py               # Fundamental: roa_at(), roa_history() + register_metric(per_share_*=None)
    ├── roic.py              # Fundamental: roic_at(), roic_history() + register_metric(per_share_*=None)
    ├── gross_margin.py      # Fundamental: gross_margin_at(), gross_margin_history() + register_metric(per_share_*=None)
    └── operating_margin.py  # Fundamental: operating_margin_at(), operating_margin_history() + register_metric(per_share_*=None)
```

---

## 🗂️ Engine Inventory (by category)

The `category` field on `EngineSpec` (introduced in v1.4.1) groups engines by financial statement / data domain. Use `list_engines(category="dre")` to filter.

| Category | Engines | Description |
|---|---|---|
| `market` | price, dividends | B3 market data (COTAHIST daily close, B3 cash_dividends DPA TTM) |
| `shares` | shares | FRE shares outstanding (+ investsite fallback when FRE NULL) |
| `dre` | earnings, revenue, gross_profit, ebit, tax | DRE statement flows (all TTM derivation, ~5 engines by 3.11, 3.01, 3.03, 3.05, 3.08) |
| `bpa` | assets, cash | BPA statement balances (snapshots — 1.01 Ativo Total, 1.01.01 Caixa) |
| `bpp` | pl, debt | BPP statement balances (snapshots — 2.03 PL, 2.01.04+2.02.01 Debt) |
| `dfc` | da | DFC statement flow (description-based search for `%deprec%` OR `%amort%`, TTM derivation) |

**Total: 13 engines in 6 categories.** When we reach 15+ engines, we may move to subfolders (`engines/dre/`, `engines/bpa/`, etc.) — until then, the `category` field gives organizational clarity without breaking import paths.

---

## 📊 Metric Inventory (by type)

| Type | Metric | Per-share | Ratio | Bonus | Engines |
|---|---|---|---|---|---|
| Per-share + price ratio | `lpa` | LPA | P/L | — | price + earnings + shares |
| Per-share + price ratio | `vpa` | VPA | P/VPA | — | price + pl + shares |
| Per-share + price ratio | `dpa` | DPA | Div Yield | Payout | price + dividends + earnings + shares |
| Per-share + price ratio | `rps` | RPS | PSR | — | price + revenue + shares |
| Per-share + price ratio | `ev_ebitda` | EBITDA/Ação | EV/EBITDA | — | price + shares + debt + cash + ebit + da (6 engines) |
| Fundamental ratio | `roe` | — | ROE | — | earnings + pl |
| Fundamental ratio | `roa` | — | ROA | — | earnings + assets |
| Fundamental ratio | `roic` | — | ROIC | — | ebit + tax + pl + debt + cash (5 engines, v1.9 subtracts cash) |
| Fundamental ratio | `gross_margin` | — | Margem Bruta | — | gross_profit + revenue |
| Fundamental ratio | `operating_margin` | — | Margem Operacional | — | ebit + revenue |

**Total: 10 metrics — 5 per-share+ratio + 5 fundamental.** All metrics expose Portuguese aliases (e.g., `margem_bruta`, `retorno_pl`, `retorno_ativos`, `retorno_capital_investido`) plus English aliases (`return_on_equity`, etc.) so users can dispatch via either language.

---

## 🤖 Central Auto-Discovery + Registry Design

### Why a central registry?

Before v1.3, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.

In v1.3, the registry moved to the **top level** (`skills/cvm/historical/_registry.py`) and handles BOTH engines and metrics. In v1.4.1, the `category` field was added to `EngineSpec` so engines could be grouped + filtered. In v1.7, `per_share_*` fields on `MetricSpec` became optional, enabling fundamental-ratio metrics. This gives:
- **Consistent pattern** — both layers self-register via `register_engine()` / `register_metric()`
- **Single source of truth** — one file holds all specs + auto-discovery logic + category metadata
- **Engine discoverability** — `list_engines()` + `list_engines(category=...)` enable docs auto-generation + backtest skill discovery by statement type
- **Metric type flexibility** — fundamental ratios skip per-share fields cleanly via `None`
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
# engines/da.py — self-registration at module level (dfc category)
from skills.cvm.historical._registry import EngineSpec, register_engine

register_engine(EngineSpec(
    name="da",
    quantity="ttm_da",
    at_fn=da_at,
    periods_fn=da_periods,
    source="DFP + ITR DFC (Depreciação e Amortização by description search, TTM)",
    category="dfc",  # NEW in v1.4.1
))
```

```python
# metrics/roic.py — fundamental ratio (per_share_* = None, NEW in v1.7)
from skills.cvm.historical._registry import MetricSpec, register_metric

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

### Auto-generation chain

When a new metric is registered, the following auto-generate:
1. **`<metric>_history` mode in MANIFEST** — `_build_metric_modes()` in `__init__.py` iterates `METRICS`
2. **`<metric>_history` function in historical.py** — `_make_metric_history_fn()` generates functions via `globals()`
3. **`historical_<metric>_chart` adapter** — `adapters/historical.py` iterates `METRICS` and auto-registers. The adapter inspects `spec.per_share_label`: if `None`, single-dataset chart (fundamental); if set, dual-axis chart (per-share + ratio).
4. **`ratio_history(metric=<name>)` dispatch** — `resolve_metric()` handles canonical + alias names
5. **`summary(metric=<name>)` metric-awareness** — `resolve_metric()` returns the spec, summary reads labels + keys from it (skips per-share KPI/row when `per_share_label` is `None`)

**Adding a metric = drop a file in metrics/ + `register_metric()`.** Zero edits to `__init__.py`, `historical.py`, or `adapters/historical.py`.

---

## 🔢 Algorithms

### TTM derivation (flow engines: earnings, revenue, gross_profit, ebit, tax, da)

All DRE/DFC flow engines use the same TTM algorithm — they differ only in the CVM account code (or descricao for `da`). Derived for any historical date:

```
For date D, find the most recent ITR period (data_fim_exerc <= D):

  ITR current period (e.g., Q2 2024, meses=6) = cumulative H1 2024 flow
  ITR prior year same period (Q2 2023, meses=6) = cumulative H1 2023 flow
  DFP prior year (2023, meses=12) = full year 2023 flow

  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1
       = (full year 2023) - (H1 2023) + (H1 2024)
       = 12 months ending 2024-06-30
```

Edge cases (handled in each engine's `_at()` function):
- No ITR before date → fall back to DFP annual value
- No ITR for prior-year same period → use DFP directly as approximation
- No DFP for prior year → return None (can't derive TTM)

### Snapshot (balance engines: pl, assets, cash, debt)

Balance-sheet engines are simpler — no TTM derivation. Just find the most recent snapshot with `data_fim_exerc <= date`.

```
For date D:
  1. Query DFP (meses=12) → annual snapshots at Dec 31
  2. Query ITR (meses=3/6/9) → quarterly snapshots at Mar/Jun/Sep 30
  3. Merge all snapshots, find most recent with data_fim_exerc <= D
  4. Return that value
```

Between snapshots (~4 per year), the balance is constant — perfect for step-function optimization in metrics.

### Multi-code sum (debt engine)

Debt is the sum of two BPP accounts:
- `2.01.04` = Empréstimos e Financiamentos (current / short-term debt)
- `2.02.01` = Empréstimos e Financiamentos (non-current / long-term debt)

The engine queries both codes via `codigo IN (..., ...)` and sums them per snapshot date. The result is a single "total debt" value per date — same shape as `pl_at()`/`assets_at()` from the consumer's perspective.

### Description-based search (da engine — first of its kind)

D&A (Depreciação e Amortização) does not have a single standardized CVM account code in the DFC. Different filers use different `codigo` values (e.g., 6.01.01.02 in DFC_MD, varying codes in DFC_MI) and some filers split D&A into multiple line items. To handle this, the `da` engine:

1. **Searches by DESCRIPTION, not by codigo:** `LOWER(c.descricao) LIKE '%deprec%' OR LOWER(c.descricao) LIKE '%amort%'`
2. **Filters by grupo:** `c.grupo LIKE '%Fluxo de Caixa%'` (matches both DFC_MI and DFC_MD)
3. **SUMs all matching line items per period** (there may be multiple per filer)
4. **Applies TTM derivation** (D&A is a flow, like earnings/revenue)

This is the only engine that uses description-based search. The pattern is intentionally NOT reused in metrics — metrics compose engines by their `at_fn`/`periods_fn` and should never re-query raw DFC data with description filters.

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

### ROIC (roic.py — v1.9 update)

ROIC = NOPAT / Invested Capital, where:
- NOPAT = EBIT − max(0, −tax)  (tax is typically negative on DRE; we use the positive expense)
- Invested Capital = PL + Debt − Cash  **(v1.9: now subtracts cash)**

```
For date D:
  ebit        = ebit_at(company, D)
  tax_expense = max(0, -tax_at(company, D))   # positive expense
  nopat       = ebit - tax_expense
  ic          = pl_at(company, D) + debt_at(company, D) - cash_at(company, D)
  ROIC        = nopat / ic
```

**v1.9 cash subtraction:** excess cash is not "invested capital", so subtracting it makes ROIC more accurate. The cash call is wrapped in `try/except Exception` and falls back to `PL + Debt` (v1.8 behavior) if cash data is unavailable — this keeps the metric robust when the cash engine isn't mocked in tests. See INSTRUCTIONS.md anti-patterns (v1.9 lesson) for why this matters.

---

## 📊 Data Flow (example: ev_ebitda_history — most complex metric)

```
ev_ebitda_history("PETR4", "2020-01-01", "2024-12-31")
  │
  ├── price_series("PETR4", "2020-01-01", "2024-12-31")
  │     → COTAHIST: ~1200 daily close prices
  │
  ├── shares_periods("PETR4")  → FRE: step function [{date, shares}, ...]    (~1/year)
  ├── debt_periods("PETR4")    → DFP+ITR BPP 2.01.04+2.02.01: step function  (~4/year)
  ├── cash_periods("PETR4")    → DFP+ITR BPA 1.01.01: step function          (~4/year)
  ├── ebit_periods("PETR4")    → DFP+ITR DRE 3.05: step function             (~4/year)
  ├── da_periods("PETR4")      → DFP+ITR DFC %deprec%/%amort%: step function (~4/year)
  │
  └── For each daily price:
        find most recent shares, debt, cash, ebit, da (step function lookups)
        EBITDA       = ebit + da
        EBITDA/share = EBITDA / shares
        EV           = price × shares + debt - cash
        EV/EBITDA    = EV / EBITDA
        → [{date, price, ebitda_ps, ev_ebitda, ebit, da, debt, cash, shares}, ...]
```

Fundamental metrics (roe, roa, roic, gross_margin, operating_margin) follow a different shape — no daily price driver, so the series is built from the union of engine period dates (~4-8 points/year) rather than 1200 daily points.

---

## 💡 Key Design Patterns

1. **Central `_registry.py` (auto-discovery for both engines + metrics)** — lives at the skill top level so it can glob BOTH `engines/*.py` AND `metrics/*.py`. Single source of truth. Modeled after `tools/report_ops/_registry.py`.
2. **Engine categories (market, shares, dre, bpa, bpp, dfc)** — the `category` field on `EngineSpec` (v1.4.1) groups engines by financial statement / data domain. `list_engines(category="dre")` filters by DRE. Enables backtest discovery by statement type. Subfolders deferred until 15+ engines.
3. **TTM derivation (flow engines)** — earnings, revenue, gross_profit, ebit, tax, da all use the same `DFP_prior_year - ITR_prior_year_same_period + ITR_current_period` algorithm. Only the CVM account code (or descricao for `da`) differs.
4. **Snapshot (balance engines)** — pl, assets, cash, debt are point-in-time balances. Simpler than flows: just find the most recent snapshot `<= date`. ~4 snapshots per year.
5. **Description-based search (da engine — first of its kind)** — D&A has no single CVM code in the DFC. The `da` engine searches by `descricao LIKE '%deprec%' OR '%amort%'` and SUMs matches per period. Pattern is intentionally NOT reused in metrics — only in engines.
6. **Multi-code sum (debt engine)** — total debt = BPP `2.01.04` (current) + `2.02.01` (non-current). The engine queries both codes via `IN (...)` and sums per date. Same external shape as other snapshot engines.
7. **Step-function optimization (all metrics)** — flows change ~4×/year, balances ~4×/year, shares ~1×/year, dividends on payment dates. Precompute step functions via `*_periods()`, do O(1) lookups per day. (Exception: DPA TTM is a rolling 365-day window, recomputed per day via a single SQL query.)
8. **Dual-axis charts (per-share+ratio) vs single-dataset (fundamental)** — the chart adapter inspects `spec.per_share_label`: if `None`, single-dataset chart with one Y axis (fundamental ratio); if set, dual-dataset chart with per-share on left axis + ratio on right axis.
9. **Flexible MetricSpec (per_share fields optional)** — `per_share_label`, `per_share_key`, `per_share_fn` are all `None` for fundamental ratios (roe, roa, roic, gross_margin, operating_margin). The same `_metric_history()` + adapter + summary code path handles both types via `None` checks.
10. **Portuguese + English aliases** — every metric exposes both (e.g., `["return_on_equity", "retorno_pl", "retorno_patrimonio"]` for ROE). Users dispatch via `summary(metric="retorno_pl")` or `summary(metric="roe")` interchangeably.

**Other established decisions (carried from v1.0-v1.3):**
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`. Consistent pattern.
- **Engines are standalone** — imported independently by any skill (e.g., future backtest). No coupling to `historical.py` or to each other.
- **Metrics compose engines** — `lpa.py` imports `price + earnings + shares`. `ev_ebitda.py` imports 6 engines (most complex). `roic.py` imports 5 engines.
- **parse_escala applied** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Engines apply `parse_escala` to convert to BRL.
- **Negative earnings/equity → None ratio** — When TTM earnings <= 0 (P/L, Payout, ROE, ROA) or PL <= 0 (P/VPA, ROE) or EBIT <= 0 (ROIC, Operating Margin) or revenue <= 0 (RPS, Margins), the ratio is meaningless. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
- **0.0 vs None for DPA** — 0.0 means "company exists but pays no dividends" (valid, yield = 0). None means "no dividends data available" (can't compute). The dividends engine distinguishes these.
- **Auto-generated MANIFEST modes** — `<metric>_history` modes appear in the MANIFEST automatically when a metric is registered. No manual editing.
- **Auto-registered chart adapters** — `historical_<metric>_chart` adapters auto-register. Each produces dual-axis (per-share+ratio) OR single-dataset (fundamental) charts based on `per_share_label`.
- **Lazy metric imports** — `historical.py` resolves metrics via the registry (`resolve_metric()`), not at module top. This keeps the import graph clean.

---

## ➕ How to Add a New Engine

1. Create a new file in `engines/` (e.g., `working_capital.py`).
2. Query your data source directly (DFP/ITR/FRE/COTAHIST/B3). Apply `parse_escala` to raw CVM values. Use `connect_dfp` / `connect_itr` / `connect_fre` from `data_sources/cvm/_db.py`, or `data_sources.b3.dividends.catalog.connect` for B3 dividends. Resolve tickers via `data_sources.cvm._bridge.resolve_company()`.
3. Implement `<quantity>_at(company, date)` and `<quantity>_periods(company)` following the engine contract.
4. Call `register_engine(EngineSpec(...))` at module level. **Set `category`** to one of: `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc`, or `other`.
5. Add tests in `tests/skills/cvm/historical/` (mock the DB connection).
6. **NEVER edit `engines/__init__.py`** — there is no manual inventory. The registry is the source of truth. `list_engines()` + `list_engine_categories()` give the live inventory.
7. **NEVER import a metric from an engine.** Engines are below metrics in the dependency graph.

---

## ➕ How to Add a New Metric

1. **Confirm the engines you need already exist.** If not, add the ENGINE first.
2. Create `metrics/<name>.py` with:
   - For **per-share+ratio** metrics: `<name>_at(company, date)` (per-share value) + `<ratio>_at(company, date)` (price ratio) + optional `<bonus>_at(company, date)` + `<name>_history(company, date_from, date_to)` (daily series with per-share + ratio + bonus ratios)
   - For **fundamental ratio** metrics: `<ratio>_at(company, date)` (ratio) + `<name>_history(company, date_from, date_to)` (series based on union of engine period dates — no daily price driver)
3. Call `register_metric(MetricSpec(...))` at module level. For fundamental ratios, set `per_share_label=None`, `per_share_key=None`, `per_share_fn=None`. Include both Portuguese + English aliases.
4. **That's it.** The following auto-generate:
   - `<name>_history` mode in the MANIFEST
   - `<name>_history` function in `historical.py`
   - `historical_<name>_chart` adapter in `adapters/historical.py` (dual-axis if `per_share_label` is set, single-dataset if `None`)
   - `ratio_history(metric=<name>)` dispatch (via `resolve_metric`)
   - `summary(metric=<name>)` metric-awareness (via `resolve_metric` — skips per-share KPI/row when `per_share_label` is `None`)
5. Add tests in `tests/skills/cvm/historical/test_<name>.py`:
   - Mock the registry spec's history_fn: `monkeypatch.setattr(METRICS["<name>"], "history_fn", fake_fn)`
   - **Mock ALL engines the metric composes** — not just some. If your metric calls `cash_at` (like ROIC does), mock it too, OR rely on the `try/except` wrapper if the metric has one.
6. Update `docs/skills/cvm/historical/` (API.md + CHANGELOG.md).

---

## 🔮 Backtest Foundation

The engines are designed for reuse by a future `skills/cvm/backtest/` skill:

```python
# Future backtest skill — reuses the same 13 engines + 10 metrics
from skills.cvm.historical.engines.price import price_at
from skills.cvm.historical.metrics.lpa import lpa_at, pe_at
from skills.cvm.historical.metrics.vpa import vpa_at, pvpa_at
from skills.cvm.historical.metrics.dpa import dpa_at, dy_at, payout_at
from skills.cvm.historical.metrics.rps import rps_at, psr_at
from skills.cvm.historical.metrics.ev_ebitda import ebitda_ps_at, ev_ebitda_at
from skills.cvm.historical.metrics.roe import roe_at
from skills.cvm.historical.metrics.roa import roa_at
from skills.cvm.historical.metrics.roic import roic_at
from skills.cvm.historical.metrics.gross_margin import gross_margin_at
from skills.cvm.historical.metrics.operating_margin import operating_margin_at

# Per-share+ratio signals: buy when P/L < 5 AND P/VPA < 1.0 AND Div Yield > 5%
if (pe_at("PETR4", "2022-06-30") < 5
    and pvpa_at("PETR4", "2022-06-30") < 1.0
    and dy_at("PETR4", "2022-06-30") > 0.05):
    entry_price = price_at("PETR4", "2022-06-30")
    # ... compute returns

# Fundamental signals: buy when ROIC > 15% AND Operating Margin > 10%
if (roic_at("PETR4", "2022-06-30") > 0.15
    and operating_margin_at("PETR4", "2022-06-30") > 0.10):
    ...

# Per-share values directly: strong dividend + cheap on EV/EBITDA
if (dpa_at("PETR4", "2022-06-30") > 1.50
    and ev_ebitda_at("PETR4", "2022-06-30") < 6):
    ...
```

No duplication — the backtest skill reuses the same engines and metrics. `list_engines(category=...)` enables discovery by statement type (e.g., "give me all DRE flow engines for a custom signal").

---

## 📐 Pattern Template Checklist (when copying to a new skill)

If you're creating a new skill that follows this pattern, here are the 10 items to set up:

1. **`_registry.py` (top level)** — `EngineSpec` (with `category`) + `MetricSpec` (with optional `per_share_*`) + `register_engine` + `register_metric` + auto-discovery (globs both `engines/` and `metrics/`) + `resolve_metric` + aliases + `list_engines(category=...)` + `list_metrics()` + `list_engine_categories()`.
2. **`engines/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory list).
3. **`engines/<quantity>.py`** — one per raw quantity, follows engine contract + `register_engine(EngineSpec(..., category="..."))` at module level. Categories are domain-specific (this skill uses `market`/`shares`/`dre`/`bpa`/`bpp`/`dfc`).
4. **`metrics/__init__.py`** — minimal docstring (NO auto-discovery code, NO manual inventory list).
5. **`metrics/<name>.py`** — one per metric, calls `register_metric(MetricSpec(...))` at module level. Use `per_share_*=None` for fundamental ratios. Include Portuguese + English aliases.
6. **`<skill>.py`** — `_metric_history()` reads from registry, auto-generates `<metric>_history` functions. Handle BOTH per-share+ratio and fundamental metrics via `spec.per_share_key` None-check.
7. **`__init__.py`** (skill manifest) — MANIFEST modes auto-generate from registry (`_build_metric_modes()` iterates `METRICS`).
8. **`adapters/<skill>.py`** — chart adapters auto-register from registry. Inspect `spec.per_share_label`: dual-axis if set, single-dataset if `None`.
9. **Tests** — mock the registry spec (not the module function): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`. Mock ALL engines a metric composes — or use `try/except` if the metric supports missing engines.
10. **Docs** — document the central registry + engine/metric separation + auto-discovery + categories + metric types (per-share+ratio vs fundamental). Include the dependency graph showing how metrics compose engines.

---

*Last updated: v1.9. See [API.md](API.md) for mode details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
