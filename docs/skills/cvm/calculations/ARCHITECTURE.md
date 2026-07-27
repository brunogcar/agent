<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🏗️ Architecture

The calculations library is the **shared engine + metric layer** between raw `data_sources/` and the user-facing CVM skills. It is the **pattern template** for central auto-discovery + registry architecture — the central `_registry.py`, engine/metric separation, and self-registration pattern are designed to be copied by other skills that need extensibility.

**Current scope (v1.0):** 16 engines in 6 categories (market, shares, dre, bpa, bpp, dfc) + 17 metrics in 2 types (5 per-share+ratio and 12 fundamental ratio).

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `skills/cvm/calculations/_registry.py` | **Central registry** — `EngineSpec` + `MetricSpec` dataclasses + `register_engine()` / `register_metric()` + auto-discovery (globs `engines/` + `metrics/`) + `resolve_metric()` + `list_engines(category=...)` + `list_engine_categories()` + `list_metrics()` + `list_all_metric_names()`. Single source of truth. |
| `skills/cvm/calculations/engines/__init__.py` | Minimal docstring (NO auto-discovery code, NO manual inventory). Auto-discovery is in `_registry.py`. |
| `skills/cvm/calculations/engines/price.py` | **market** — COTAHIST daily close: `price_at()`, `price_series()` |
| `skills/cvm/calculations/engines/dividends.py` | **market** — B3 cash_dividends DPA TTM: `dividends_at()`, `dividends_periods()` |
| `skills/cvm/calculations/engines/shares.py` | **shares** — FRE shares outstanding (+ investsite.com.br fallback when FRE NULL): `shares_at()`, `shares_periods()` |
| `skills/cvm/calculations/engines/earnings.py` | **dre** — TTM earnings (DFP+ITR DRE 3.11): `ttm_earnings_at()`, `ttm_earnings_periods()` |
| `skills/cvm/calculations/engines/revenue.py` | **dre** — TTM net revenue (DFP+ITR DRE 3.01): `revenue_at()`, `revenue_periods()` |
| `skills/cvm/calculations/engines/gross_profit.py` | **dre** — TTM gross profit (DFP+ITR DRE 3.03): `gross_profit_at()`, `gross_profit_periods()` |
| `skills/cvm/calculations/engines/ebit.py` | **dre** — TTM EBIT (DFP+ITR DRE 3.05): `ebit_at()`, `ebit_periods()` |
| `skills/cvm/calculations/engines/tax.py` | **dre** — TTM IR+CSLL (DFP+ITR DRE 3.08, typically negative): `tax_at()`, `tax_periods()` |
| `skills/cvm/calculations/engines/assets.py` | **bpa** — Ativo snapshot (DFP+ITR BPA 1.01): `assets_at()`, `assets_periods()` |
| `skills/cvm/calculations/engines/cash.py` | **bpa** — Caixa e Equivalentes snapshot (DFP+ITR BPA 1.01.01): `cash_at()`, `cash_periods()` |
| `skills/cvm/calculations/engines/total_assets.py` | **bpa** — Ativo Total snapshot (DFP+ITR BPA 1): `total_assets_at()`, `total_assets_periods()` |
| `skills/cvm/calculations/engines/pl.py` | **bpp** — PL snapshot (DFP+ITR BPP 2.03): `pl_at()`, `pl_periods()` |
| `skills/cvm/calculations/engines/debt.py` | **bpp** — Debt snapshot (DFP+ITR BPP 2.01.04+2.02.01, multi-code sum): `debt_at()`, `debt_periods()` |
| `skills/cvm/calculations/engines/current_liabilities.py` | **bpp** — Passivo Circulante snapshot (DFP+ITR BPP 2.01): `current_liabilities_at()`, `current_liabilities_periods()` |
| `skills/cvm/calculations/engines/da.py` | **dfc** — TTM D&A via description-based search (`%deprec%` OR `%amort%`): `da_at()`, `da_periods()` |
| `skills/cvm/calculations/engines/capex.py` | **dfc** — TTM CapEx via description-based search (`%imobilizado%` OR `%intangivel%`): `capex_at()`, `capex_periods()` |
| `skills/cvm/calculations/metrics/__init__.py` | Minimal docstring (NO auto-discovery code, NO manual inventory). |
| `skills/cvm/calculations/metrics/lpa.py` | **Per-share+ratio** — LPA + P/L: `lpa_at()`, `pe_at()`, `lpa_history()`. Engines: price + earnings + shares. |
| `skills/cvm/calculations/metrics/vpa.py` | **Per-share+ratio** — VPA + P/VPA: `vpa_at()`, `pvpa_at()`, `vpa_history()`. Engines: price + pl + shares. |
| `skills/cvm/calculations/metrics/dpa.py` | **Per-share+ratio** — DPA + Div Yield + Payout (bonus): `dpa_at()`, `dy_at()`, `payout_at()`, `dpa_history()`. Engines: price + dividends + earnings + shares. |
| `skills/cvm/calculations/metrics/rps.py` | **Per-share+ratio** — RPS + PSR: `rps_at()`, `psr_at()`, `rps_history()`. Engines: price + revenue + shares. |
| `skills/cvm/calculations/metrics/ev_ebitda.py` | **Per-share+ratio** — EBITDA/Ação + EV/EBITDA: `ebitda_ps_at()`, `ev_ebitda_at()`, `ev_ebitda_history()`. Engines: price + shares + debt + cash + ebit + da (6 engines, most complex). |
| `skills/cvm/calculations/metrics/roe.py` | **Fundamental** — ROE = earnings/PL: `roe_at()`, `roe_history()`. Engines: earnings + pl. |
| `skills/cvm/calculations/metrics/roa.py` | **Fundamental** — ROA = earnings/assets: `roa_at()`, `roa_history()`. Engines: earnings + assets. |
| `skills/cvm/calculations/metrics/roic.py` | **Fundamental** — ROIC = NOPAT/(PL+Debt−Cash): `roic_at()`, `roic_history()`. Engines: ebit + tax + pl + debt + cash (5 engines, v1.9 subtracts cash via `try/except`). |
| `skills/cvm/calculations/metrics/gross_margin.py` | **Fundamental** — Margem Bruta = gross_profit/revenue: `gross_margin_at()`, `gross_margin_history()`. Engines: gross_profit + revenue. |
| `skills/cvm/calculations/metrics/operating_margin.py` | **Fundamental** — Margem Operacional = EBIT/revenue: `operating_margin_at()`, `operating_margin_history()`. Engines: ebit + revenue. |
| `skills/cvm/calculations/metrics/net_margin.py` | **Fundamental** — Margem Líquida = earnings/revenue: `net_margin_at()`, `net_margin_history()`. Engines: earnings + revenue. |
| `skills/cvm/calculations/metrics/ebitda_margin.py` | **Fundamental** — Margem EBITDA = (EBIT+D&A)/revenue: `ebitda_margin_at()`, `ebitda_margin_history()`. Engines: ebit + da + revenue. |
| `skills/cvm/calculations/metrics/debt_equity.py` | **Fundamental** — Dívida/PL = debt/pl: `debt_equity_at()`, `debt_equity_history()`. Engines: debt + pl. |
| `skills/cvm/calculations/metrics/net_debt_ebitda.py` | **Fundamental** — DL/EBITDA = (debt−cash)/(EBIT+D&A): `net_debt_ebitda_at()`, `net_debt_ebitda_history()`. Engines: debt + cash + ebit + da. |
| `skills/cvm/calculations/metrics/asset_turnover.py` | **Fundamental** — Giro de Ativos = revenue/assets: `asset_turnover_at()`, `asset_turnover_history()`. Engines: revenue + assets. |
| `skills/cvm/calculations/metrics/capex_revenue.py` | **Fundamental** — CapEx/Receita = capex/revenue: `capex_revenue_at()`, `capex_revenue_history()`. Engines: capex + revenue. |
| `skills/cvm/calculations/metrics/current_ratio.py` | **Fundamental** — Liquidez Corrente = assets/current_liabilities: `current_ratio_at()`, `current_ratio_history()`. Engines: assets + current_liabilities. |

---

## 🌳 Module Tree

```text
skills/cvm/calculations/
├── _registry.py                 # CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories
├── engines/
│   ├── __init__.py              # Minimal docstring (auto-discovery is in _registry.py)
│   ├── price.py                 # market — COTAHIST: price_at(), price_series() + register_engine(category="market")
│   ├── dividends.py             # market — B3 cash_dividends: dividends_at(), dividends_periods() + register_engine(category="market")
│   ├── shares.py                # shares — FRE + investsite fallback: shares_at(), shares_periods() + register_engine(category="shares")
│   ├── earnings.py              # dre — DFP+ITR 3.11 TTM: ttm_earnings_at(), ttm_earnings_periods() + register_engine(category="dre")
│   ├── revenue.py               # dre — DFP+ITR 3.01 TTM: revenue_at(), revenue_periods() + register_engine(category="dre")
│   ├── gross_profit.py          # dre — DFP+ITR 3.03 TTM: gross_profit_at(), gross_profit_periods() + register_engine(category="dre")
│   ├── ebit.py                  # dre — DFP+ITR 3.05 TTM: ebit_at(), ebit_periods() + register_engine(category="dre")
│   ├── tax.py                   # dre — DFP+ITR 3.08 TTM: tax_at(), tax_periods() + register_engine(category="dre")
│   ├── assets.py                # bpa — DFP+ITR BPA 1.01 snapshot: assets_at(), assets_periods() + register_engine(category="bpa")
│   ├── cash.py                  # bpa — DFP+ITR BPA 1.01.01 snapshot: cash_at(), cash_periods() + register_engine(category="bpa")
│   ├── total_assets.py          # bpa — DFP+ITR BPA 1 snapshot: total_assets_at(), total_assets_periods() + register_engine(category="bpa")
│   ├── pl.py                    # bpp — DFP+ITR BPP 2.03 snapshot: pl_at(), pl_periods() + register_engine(category="bpp")
│   ├── debt.py                  # bpp — DFP+ITR BPP 2.01.04+2.02.01 snapshot (multi-code sum): debt_at(), debt_periods() + register_engine(category="bpp")
│   ├── current_liabilities.py   # bpp — DFP+ITR BPP 2.01 snapshot: current_liabilities_at(), current_liabilities_periods() + register_engine(category="bpp")
│   ├── da.py                    # dfc — DFP+ITR DFC %deprec%/%amort% TTM (description search): da_at(), da_periods() + register_engine(category="dfc")
│   └── capex.py                 # dfc — DFP+ITR DFC %imobilizado%/%intangivel% TTM (description search): capex_at(), capex_periods() + register_engine(category="dfc")
└── metrics/
    ├── __init__.py              # Minimal docstring (auto-discovery is in _registry.py)
    ├── lpa.py                   # Per-share+ratio: lpa_at(), pe_at(), lpa_history() + register_metric()
    ├── vpa.py                   # Per-share+ratio: vpa_at(), pvpa_at(), vpa_history() + register_metric()
    ├── dpa.py                   # Per-share+ratio: dpa_at(), dy_at(), payout_at(), dpa_history() + register_metric()
    ├── rps.py                   # Per-share+ratio: rps_at(), psr_at(), rps_history() + register_metric()
    ├── ev_ebitda.py             # Per-share+ratio: ebitda_ps_at(), ev_ebitda_at(), ev_ebitda_history() + register_metric()
    ├── roe.py                   # Fundamental: roe_at(), roe_history() + register_metric(per_share_*=None)
    ├── roa.py                   # Fundamental: roa_at(), roa_history() + register_metric(per_share_*=None)
    ├── roic.py                  # Fundamental: roic_at(), roic_history() + register_metric(per_share_*=None)
    ├── gross_margin.py          # Fundamental: gross_margin_at(), gross_margin_history() + register_metric(per_share_*=None)
    ├── operating_margin.py      # Fundamental: operating_margin_at(), operating_margin_history() + register_metric(per_share_*=None)
    ├── net_margin.py            # Fundamental: net_margin_at(), net_margin_history() + register_metric(per_share_*=None)
    ├── ebitda_margin.py         # Fundamental: ebitda_margin_at(), ebitda_margin_history() + register_metric(per_share_*=None)
    ├── debt_equity.py           # Fundamental: debt_equity_at(), debt_equity_history() + register_metric(per_share_*=None)
    ├── net_debt_ebitda.py       # Fundamental: net_debt_ebitda_at(), net_debt_ebitda_history() + register_metric(per_share_*=None)
    ├── asset_turnover.py        # Fundamental: asset_turnover_at(), asset_turnover_history() + register_metric(per_share_*=None)
    ├── capex_revenue.py         # Fundamental: capex_revenue_at(), capex_revenue_history() + register_metric(per_share_*=None)
    └── current_ratio.py         # Fundamental: current_ratio_at(), current_ratio_history() + register_metric(per_share_*=None)
```

---

## 🧪 Test Tree

```text
tests/skills/cvm/
├── conftest.py                              # Autouse env vars (PLANNER_MODEL etc.) so core.config loads during collection
├── calculations/                            # ← calculations library tests (split by metric name in v1.0)
│   ├── conftest.py                          # Same env vars fixture (kept per-subfolder for isolation)
│   ├── test_engines.py                      # Engine contract: every engine has _at() + _periods() + register_engine()
│   ├── test_registry.py                     # Engine + metric auto-discovery, aliases, categories, resolve_metric
│   ├── test_lpa.py                          # LPA + P/L metric (price + earnings + shares)
│   ├── test_vpa.py                          # VPA + P/VPA metric (price + pl + shares)
│   ├── test_dpa.py                          # DPA + DY + Payout metric (price + dividends + earnings + shares)
│   ├── test_rps.py                          # RPS + PSR metric (price + revenue + shares)
│   ├── test_ev_ebitda.py                    # EV/EBITDA metric (6 engines — most complex)
│   ├── test_roe.py                          # ROE fundamental ratio (earnings + pl)
│   ├── test_roa.py                          # ROA fundamental ratio (earnings + assets)
│   ├── test_roic.py                         # ROIC fundamental ratio (ebit + tax + pl + debt + cash — v1.9 cash subtraction)
│   ├── test_gross_margin.py                 # Margem Bruta (gross_profit + revenue)
│   ├── test_operating_margin.py             # Margem Operacional (ebit + revenue)
│   ├── test_net_margin.py                   # Margem Líquida (earnings + revenue)
│   ├── test_ebitda_margin.py                # Margem EBITDA (ebit + da + revenue)
│   ├── test_debt_equity.py                  # Dívida/PL (debt + pl)
│   ├── test_net_debt_ebitda.py              # DL/EBITDA (debt + cash + ebit + da)
│   ├── test_asset_turnover.py               # Giro de Ativos (revenue + assets)
│   ├── test_capex_revenue.py                # CapEx/Receita (capex + revenue)
│   └── test_current_ratio.py                # Liquidez Corrente (assets + current_liabilities)
├── historical/                              # Historical skill tests (mode dispatch, MANIFEST, route)
│   └── test_historical.py                   # Modes (lpa_history, ratio_history, summary), MANIFEST, route
├── comparison/test_comparison.py            # Comparison skill
├── dividends/test_dividends.py              # Dividends skill
├── financials/test_financials.py            # Financials skill
├── governance/test_governance.py            # Governance skill
├── insider/test_insider.py                  # Insider skill
├── screener/test_screener.py                # Screener skill
├── shareholders/test_shareholders.py        # Shareholders skill
├── valuation/test_valuation.py              # Valuation skill
└── test_integration.py                      # Cross-skill integration
```

**Test split (v1.0):** Engine/metric tests live in `tests/skills/cvm/calculations/` (split by metric name, not by tier/version). Historical skill tests now only contain `test_historical.py` (mode dispatch, MANIFEST, route). See [INSTRUCTIONS.md](INSTRUCTIONS.md) anti-patterns for the v1.0 test-split lesson.

---

## 🧱 Engine vs Metric — The Core Pattern

This library enforces a strict separation between **engines** (data access) and **metrics** (ratio math). This is the most important architectural rule. Violating it creates coupling that makes future metrics and the backtest skill impossible to reuse cleanly.

### Engines (leaves — one per raw quantity)

An engine fetches ONE raw number at any historical date from its data source(s). Engines are **leaves** — they never import each other and never import metrics.

**Engine contract (every engine follows this shape):**
- `<quantity>_at(company, date) -> float | None` — value at most recent data point <= date
- `<quantity>_periods(company) -> list[dict]` — all data points `[{"date": "...", "<quantity>": value}, ...]` sorted oldest-first (for step-function optimization)
- `register_engine(EngineSpec(...))` at module level — self-registers with the central registry

### Metrics (compose engines)

A metric imports 2+ engines and produces either:

**Type 1 — Per-share value + price ratio (+ optional bonus ratios):**
- Per-share value: LPA, VPA, DPA, RPS, EBITDA/Ação — useful on its own (e.g., backtest filters on EPS)
- Price ratio: P/L, P/VPA, Div Yield, PSR, EV/EBITDA — tells you if the stock is cheap vs history
- Optional bonus ratios: Payout (DPA/LPA) — included in the series + summary
- `<name>_history()` produces a **daily** series driven by price dates (1200+ points over 5 years)

**Type 2 — Fundamental ratio:**
- A pure ratio of two engine values, no price, no shares (e.g., ROE = earnings/PL)
- `per_share_label`, `per_share_key`, `per_share_fn` are all `None` in MetricSpec
- `<name>_history()` produces a series based on the **union of engine period dates** (~4-8 points/year — no daily price driver)

**Metric contract:**
- `<name>_at(company, date) -> float | None` — per-share value (None for fundamental ratios)
- `<ratio>_at(company, date) -> float | None` — ratio (P/L, ROE, EV/EBITDA, ...)
- Optional: `<bonus>_at(company, date)` — bonus ratio (e.g., `payout_at`)
- `<name>_history(company, date_from, date_to) -> list[dict]` — series with per-share + ratio + bonus ratios (per-share+ratio) OR ratio + engine values (fundamental)
- `register_metric(MetricSpec(...))` at module level — self-registers with the central registry

### Dependency graph (MUST stay acyclic)

```text
calculations/_registry.py  (CENTRAL: EngineSpec + MetricSpec + auto-discovery + resolve_metric + categories)
       │
       ├── engines/  (16 leaves — never import each other or metrics)
       │     ├── market: price, dividends
       │     ├── shares: shares
       │     ├── dre:    earnings, revenue, gross_profit, ebit, tax
       │     ├── bpa:    assets, cash, total_assets
       │     ├── bpp:    pl, debt, current_liabilities
       │     └── dfc:    da, capex
       │
       └── metrics/  (17 — compose engines, never point at other metrics)
             ├── lpa.py             → price + earnings + shares                       (Type 1)
             ├── vpa.py             → price + pl + shares                              (Type 1)
             ├── dpa.py             → price + dividends + earnings + shares           (Type 1, +payout)
             ├── rps.py             → price + revenue + shares                        (Type 1)
             ├── ev_ebitda.py       → price + shares + debt + cash + ebit + da        (Type 1, 6 engines)
             ├── roe.py             → earnings + pl                                    (Type 2)
             ├── roa.py             → earnings + assets                                (Type 2)
             ├── roic.py            → ebit + tax + pl + debt + cash                    (Type 2, 5 engines, v1.9 cash)
             ├── gross_margin.py    → gross_profit + revenue                           (Type 2)
             ├── operating_margin.py → ebit + revenue                                 (Type 2)
             ├── net_margin.py      → earnings + revenue                               (Type 2)
             ├── ebitda_margin.py   → ebit + da + revenue                              (Type 2)
             ├── debt_equity.py     → debt + pl                                        (Type 2)
             ├── net_debt_ebitda.py → debt + cash + ebit + da                          (Type 2, 4 engines)
             ├── asset_turnover.py  → revenue + assets                                 (Type 2)
             ├── capex_revenue.py   → capex + revenue                                  (Type 2)
             └── current_ratio.py   → assets + current_liabilities                     (Type 2)

       (engines never point upward — they're leaves)
```

Engines never point upward. Metrics never point at other metrics. Consumer skills (`historical.py`, `valuation.py`, etc.) are the only modules that know about both engines and metrics together (via the central registry).

**Exception (v1.9 — ROIC + cash):** ROIC imports the `cash` engine *lazily inside a function body* with `try/except Exception:` so tests that don't mock `cash_at` still pass. This is the ONLY metric→engine lazy import; all other metrics import their engines at module top. The pattern is reserved for metrics that ADD an engine to an existing composition (like ROIC adding cash in v1.9). See [INSTRUCTIONS.md](INSTRUCTIONS.md) anti-patterns for the v1.9 lesson.

---

## 🗂️ Engine Inventory (by category)

The `category` field on `EngineSpec` (introduced in v1.4.1) groups engines by financial statement / data domain. Use `list_engines(category="dre")` to filter.

| Category | Engines | Description |
|---|---|---|
| `market` | price, dividends | B3 market data (COTAHIST daily close, B3 cash_dividends DPA TTM) |
| `shares` | shares | FRE shares outstanding (+ investsite.com.br fallback when FRE NULL) |
| `dre` | earnings, revenue, gross_profit, ebit, tax | DRE statement flows (all TTM derivation, 5 engines by 3.11, 3.01, 3.03, 3.05, 3.08) |
| `bpa` | assets, cash, total_assets | BPA statement balances (snapshots — 1.01 Ativo, 1.01.01 Caixa, 1 Ativo Total) |
| `bpp` | pl, debt, current_liabilities | BPP statement balances (snapshots — 2.03 PL, 2.01.04+2.02.01 Debt, 2.01 Passivo Circulante) |
| `dfc` | da, capex | DFC statement flows (description-based search — `%deprec%`/`%amort%` for D&A, `%imobilizado%`/`%intangivel%` for CapEx; TTM derivation) |

**Total: 16 engines in 6 categories.** When we reach 20+ engines, we may move to subfolders (`engines/dre/`, `engines/bpa/`, etc.) — until then, the `category` field gives organizational clarity without breaking import paths.

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
| Fundamental ratio | `net_margin` | — | Margem Líquida | — | earnings + revenue |
| Fundamental ratio | `ebitda_margin` | — | Margem EBITDA | — | ebit + da + revenue |
| Fundamental ratio | `debt_equity` | — | Dívida/PL | — | debt + pl |
| Fundamental ratio | `net_debt_ebitda` | — | DL/EBITDA | — | debt + cash + ebit + da |
| Fundamental ratio | `asset_turnover` | — | Giro de Ativos | — | revenue + assets |
| Fundamental ratio | `capex_revenue` | — | CapEx/Receita | — | capex + revenue |
| Fundamental ratio | `current_ratio` | — | Liquidez Corrente | — | assets + current_liabilities |

**Total: 17 metrics — 5 per-share+ratio + 12 fundamental.** All metrics expose both Portuguese aliases (e.g., `margem_bruta`, `retorno_pl`, `retorno_ativos`, `retorno_capital_investido`, `giro_ativos`, `intensidade_capex`, `liquidez_corrente`) and English aliases (`return_on_equity`, `return_on_assets`, etc.) so users can dispatch via either language. See [API.md](API.md) for the full alias table.

---

## 🤖 Central Auto-Discovery + Registry Design

### Why a central registry?

Before v1.3, the registry lived in `metrics/_registry.py` and only handled metrics. Engines had no registry — they were imported by name by metrics. This created an inconsistency: metrics self-registered, but engines didn't.

In v1.3, the registry moved to the **top level** (`skills/cvm/calculations/_registry.py`) and handled BOTH engines and metrics. In v1.0 of the calculations library (extracted from historical v2.1), the registry moved again to `skills/cvm/calculations/_registry.py` and is now shared by all CVM skills. This gives:
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
            importlib.import_module(f"skills.cvm.calculations.engines.{py_file.stem}")

    # Discover metrics (triggers register_metric calls)
    for py_file in sorted((base / "metrics").glob("*.py")):
        if py_file.name != "__init__.py":
            importlib.import_module(f"skills.cvm.calculations.metrics.{py_file.stem}")

_auto_discover()  # run at import time
```

```python
# engines/da.py — self-registration at module level (dfc category)
from skills.cvm.calculations._registry import EngineSpec, register_engine

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
# metrics/roic.py — fundamental ratio (per_share_* = None, since v1.7)
from skills.cvm.calculations._registry import MetricSpec, register_metric

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

### Auto-generation chain (for consumer skills)

When a new metric is registered, the historical skill auto-generates the following (other consumer skills will do the same in Phase 2+):
1. **`<metric>_history` mode in MANIFEST** — `_build_metric_modes()` in `historical/__init__.py` iterates `METRICS`
2. **`<metric>_history` function in historical.py** — `_make_metric_history_fn()` generates functions via `globals()`
3. **`historical_<metric>_chart` adapter** — `adapters/historical.py` iterates `METRICS` and auto-registers. The adapter inspects `spec.per_share_label`: if `None`, single-dataset chart (fundamental); if set, dual-axis chart (per-share + ratio).
4. **`ratio_history(metric=<name>)` dispatch** — `resolve_metric()` handles canonical + alias names
5. **`summary(metric=<name>)` metric-awareness** — `resolve_metric()` returns the spec, summary reads labels + keys from it (skips per-share KPI/row when `per_share_label` is `None`)

**Adding a metric = drop a file in metrics/ + `register_metric()`.** Zero edits to `__init__.py`, `historical.py`, or `adapters/historical.py`. (Consumer skills auto-generate their per-skill integration; the calculations library itself stays untouched.)

---

## 🔢 Algorithms

### TTM derivation (flow engines: earnings, revenue, gross_profit, ebit, tax, da, capex)

All DRE/DFC flow engines use the same TTM algorithm — they differ only in the CVM account code (or descricao for `da` / `capex`). Derived for any historical date:

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

### Snapshot (balance engines: pl, assets, cash, total_assets, debt, current_liabilities)

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

### Description-based search (da + capex engines — first of their kind)

D&A (Depreciação e Amortização) and CapEx (Capital Expenditure) do not have a single standardized CVM account code in the DFC. Different filers use different `codigo` values (e.g., 6.01.01.02 in DFC_MD, varying codes in DFC_MI) and some filers split them into multiple line items. To handle this, both engines:

1. **Search by DESCRIPTION, not by codigo:**
   - `da`: `LOWER(c.descricao) LIKE '%deprec%' OR LOWER(c.descricao) LIKE '%amort%'`
   - `capex`: `LOWER(c.descricao) LIKE '%imobilizado%' OR LOWER(c.descricao) LIKE '%intangivel%'`
2. **Filter by grupo:** `c.grupo LIKE '%Fluxo de Caixa%'` (matches both DFC_MI and DFC_MD)
3. **SUM all matching line items per period** (there may be multiple per filer)
4. **Apply TTM derivation** (D&A and CapEx are flows, like earnings/revenue)

This is the only engine pattern that uses description-based search. The pattern is intentionally NOT reused in metrics — metrics compose engines by their `at_fn`/`periods_fn` and should never re-query raw DFC data with description filters. If you need a new description-searched quantity, add an ENGINE for it.

### DPA TTM (dividends engine)

DPA = trailing 12-month dividends per share. The B3 `cash_dividends.rate` field is already per-share (R$/share), so we just sum rates in the 365-day window.

```
For date D:
  DPA_TTM = SUM(cash_dividends.rate WHERE event_date BETWEEN D-365 AND D)

  event_date = COALESCE(payment_date, last_date_prior, approved_on)

JCP (Juros sobre Capital Próprio) is included — it's a real cash distribution.
The label field distinguishes Dividendo vs JCP, but we sum both.
```

**Special cases:**
- No event dates at all → return `None` (no data available)
- All event dates after query date → return `None` (can't compute TTM)
- Company exists but paid nothing in the window → return `0.0` (different from `None`)

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

**v1.9 cash subtraction:** excess cash is not "invested capital", so subtracting it makes ROIC more accurate. The cash call is wrapped in `try/except Exception` and falls back to `PL + Debt` (v1.8 behavior) if cash data is unavailable — this keeps the metric robust when the cash engine isn't mocked in tests. See [INSTRUCTIONS.md](INSTRUCTIONS.md) anti-patterns (v1.9 lesson) for why this matters.

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

Fundamental metrics (roe, roa, roic, gross_margin, operating_margin, net_margin, ebitda_margin, debt_equity, net_debt_ebitda, asset_turnover, capex_revenue, current_ratio) follow a different shape — no daily price driver, so the series is built from the union of engine period dates (~4-8 points/year) rather than 1200 daily points.

---

## 💡 Key Design Patterns

1. **Central `_registry.py` (auto-discovery for both engines + metrics)** — lives at the library top level so it can glob BOTH `engines/*.py` AND `metrics/*.py`. Single source of truth. Modeled after `tools/report_ops/_registry.py`.
2. **Engine categories (market, shares, dre, bpa, bpp, dfc)** — the `category` field on `EngineSpec` (v1.4.1) groups engines by financial statement / data domain. `list_engines(category="dre")` filters by DRE. Enables backtest discovery by statement type. Subfolders deferred until 20+ engines.
3. **TTM derivation (flow engines)** — earnings, revenue, gross_profit, ebit, tax, da, capex all use the same `DFP_prior_year - ITR_prior_year_same_period + ITR_current_period` algorithm. Only the CVM account code (or descricao for da/capex) differs.
4. **Snapshot (balance engines)** — pl, assets, cash, total_assets, debt, current_liabilities are point-in-time balances. Simpler than flows: just find the most recent snapshot `<= date`. ~4 snapshots per year.
5. **Description-based search (da + capex engines — first of their kind)** — D&A and CapEx have no single CVM code in the DFC. Both engines search by descricao (`%deprec%`/`%amort%` for da, `%imobilizado%`/`%intangivel%` for capex) and SUMs matches per period. Pattern is intentionally NOT reused in metrics — only in engines.
6. **Multi-code sum (debt engine)** — total debt = BPP `2.01.04` (current) + `2.02.01` (non-current). The engine queries both codes via `IN (...)` and sums per date. Same external shape as other snapshot engines.
7. **Step-function optimization (all metrics)** — flows change ~4×/year, balances ~4×/year, shares ~1×/year, dividends on event dates. Precompute step functions via `*_periods()`, do O(1) lookups per day. (Exception: DPA TTM is a rolling 365-day window, recomputed per day via a single SQL query.)
8. **Dual-axis charts (per-share+ratio) vs single-dataset (fundamental)** — consumer skills' chart adapters inspect `spec.per_share_label`: if `None`, single-dataset chart with one Y axis (fundamental ratio); if set, dual-dataset chart with per-share on left axis + ratio on right axis.
9. **Flexible MetricSpec (per_share fields optional)** — `per_share_label`, `per_share_key`, `per_share_fn` are all `None` for fundamental ratios (12 metrics). The same `*_history()` + adapter + summary code path handles both types via `None` checks.
10. **Portuguese + English aliases** — every metric exposes both (e.g., `["return_on_equity", "retorno_pl", "retorno_patrimonio"]` for ROE). Users dispatch via `summary(metric="retorno_pl")` or `summary(metric="roe")` interchangeably.

**Other established decisions (carried from v1.0-v1.9 of the historical skill):**
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`. Consistent pattern.
- **Engines are standalone** — imported independently by any skill (historical, future valuation/financials/backtest). No coupling to consumer skills or to each other.
- **Metrics compose engines** — `lpa.py` imports `price + earnings + shares`. `ev_ebitda.py` imports 6 engines (most complex). `roic.py` imports 5 engines.
- **parse_escala applied** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Engines apply `parse_escala` (or an inline `CASE` expression) to convert to BRL.
- **Negative earnings/equity → None ratio** — When TTM earnings <= 0 (P/L, Payout, ROE, ROA, Net Margin) or PL <= 0 (P/VPA, ROE, Debt/Equity) or EBIT <= 0 (ROIC, Operating Margin, EBITDA Margin, DL/EBITDA) or revenue <= 0 (RPS, all margins, asset turnover, capex/revenue) or EBITDA <= 0 (EV/EBITDA, DL/EBITDA), the ratio is meaningless. Return None (chart shows gaps). The per-share value MAY be returned (negative LPA is a valid number).
- **0.0 vs None for DPA** — 0.0 means "company exists but pays no dividends" (valid, yield = 0). None means "no dividends data available" (can't compute). The dividends engine distinguishes these.
- **Lazy metric imports in consumer skills** — consumer skills resolve metrics via the registry (`resolve_metric()`), not at module top. This keeps the import graph clean.
- **Idempotent auto-discovery** — `_auto_discover()` uses a `_done` flag to avoid re-running on re-import (which can happen in test environments).

---

## ➕ How to Add a New Engine

1. Create a new file in `engines/` (e.g., `working_capital.py`).
2. Query your data source directly (DFP/ITR/FRE/COTAHIST/B3). Apply `parse_escala` to raw CVM values. Use `connect_dfp` / `connect_itr` / `connect_fre` from `data_sources/cvm/_db.py`, or `data_sources.b3.dividends.catalog.connect` for B3 dividends. Resolve tickers via `data_sources.cvm._bridge.resolve_company()`.
3. Implement `<quantity>_at(company, date)` and `<quantity>_periods(company)` following the engine contract.
4. Call `register_engine(EngineSpec(...))` at module level. **Set `category`** to one of: `market`, `shares`, `dre`, `bpa`, `bpp`, `dfc`, or `other`.
5. Add tests in `tests/skills/cvm/calculations/test_engines.py` (or a new `test_<name>.py`) — mock the DB connection.
6. **NEVER edit `engines/__init__.py`** — there is no manual inventory. The registry is the source of truth. `list_engines()` + `list_engine_categories()` give the live inventory.
7. **NEVER import a metric from an engine.** Engines are below metrics in the dependency graph.

---

## ➕ How to Add a New Metric

1. **Confirm the engines you need already exist.** If not, add the ENGINE first.
2. Create `metrics/<name>.py` with:
   - For **per-share+ratio** metrics (Type 1): `<name>_at(company, date)` (per-share value) + `<ratio>_at(company, date)` (price ratio) + optional `<bonus>_at(company, date)` + `<name>_history(company, date_from, date_to)` (daily series with per-share + ratio + bonus ratios)
   - For **fundamental ratio** metrics (Type 2): `<ratio>_at(company, date)` (ratio) + `<name>_history(company, date_from, date_to)` (series based on union of engine period dates — no daily price driver)
3. Call `register_metric(MetricSpec(...))` at module level. For fundamental ratios, set `per_share_label=None`, `per_share_key=None`, `per_share_fn=None`. Include both Portuguese + English aliases.
4. **That's it for the calculations library.** Consumer skills (historical, future valuation/financials/backtest) auto-generate their per-skill integration from the registry — see each consumer skill's ARCHITECTURE.md for what auto-generates there.
5. Add tests in `tests/skills/cvm/calculations/test_<name>.py`:
   - Mock the registry spec's history_fn: `monkeypatch.setattr(METRICS["<name>"], "history_fn", fake_fn)`
   - **Mock ALL engines the metric composes** — not just some. If your metric calls `cash_at` (like ROIC does), mock it too, OR rely on the `try/except` wrapper if the metric has one.
6. Update `docs/skills/cvm/calculations/` (API.md + CHANGELOG.md).

---

## 🔮 Backtest Foundation

The engines are designed for reuse by a future `skills/cvm/backtest/` skill:

```python
# Future backtest skill — reuses the same 16 engines + 17 metrics
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

## 🧪 Testing

```bash
# Run all calculations tests (engines + metrics + registry)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/calculations/ -v -W error --tb=short

# Run a single metric test
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/calculations/test_roic.py -v

# Run all CVM skill tests (calculations + historical + comparison + dividends + ...)
PLANNER_MODEL=test PLANNER_PROVIDER=test EXECUTOR_MODEL=test EXECUTOR_PROVIDER=test \
  python -m pytest tests/skills/cvm/ -v -W error --tb=short
```

**Test architecture:**
- `tests/skills/cvm/conftest.py` — autouse env var fixture (`PLANNER_MODEL=test` etc.) so `core.config` loads during collection
- `tests/skills/cvm/calculations/conftest.py` — same env vars (kept per-subfolder for isolation)
- Calculations tests mock the registry spec (not module functions): `monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_fn)`
- Mock ALL engines a metric composes — or use `try/except` if the metric supports missing engines (v1.9 ROIC+cash lesson)
- Fundamental ratio tests verify `per_share_key is None` and no `price`/`shares` in series entries
- Per-share+ratio tests verify dual-dataset yAxisID assertions (in the historical adapter tests)
- `test_engines.py` verifies every engine follows the contract: `*_at()` + `*_periods()` + `register_engine()` at module level
- `test_registry.py` verifies auto-discovery picks up all engines + metrics, aliases resolve, categories filter

**Mock Strategy:**
- `data_sources.cvm._db.connect_dfp` / `connect_itr` / `connect_fre` are patched at the engine module's import site
- `data_sources.cvm._bridge.resolve_company` is patched at each engine module
- `data_sources.b3.dividends.catalog.connect` is patched at the dividends engine
- The cotahist DB file (`cotahist.db`) is patched at the price engine's `_cotahist_db()` function
- Registry specs (`METRICS["lpa"].history_fn`, `ENGINES["price"].at_fn`) are patched when testing consumer-skill integration (e.g., historical mode dispatch)

---

*Last updated: 2026-07-26 (v1.0 — extracted from historical v2.1). See [API.md](API.md) for function signatures, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
