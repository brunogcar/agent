<- Back to [CVM Skills](../CVM.md)

# 📈 HISTORICAL — Historical Financial Ratios Skill

Computes financial ratios over time by combining **engines** (basics: price, earnings, shares, PL, dividends, etc.) into **metrics** (per-share values + price ratios + fundamental ratios: LPA+P/L, VPA+P/VPA, DPA+Div Yield+Payout, RPS+PSR, EV/EBITDA, ROE, ROA, ROIC, Margins, Leverage, Turnover, Liquidity). Tells you if a stock is cheap vs its **own history**.

**This skill is a thin wrapper over the shared `calculations/` package.** Engines, metrics, and the central registry live in [`skills/cvm/calculations/`](CALCULATIONS.md) — see [CALCULATIONS.md](CALCULATIONS.md) for the engine/metric library docs. Historical adds **mode dispatch** (`<metric>_history`, `summary`, `ratio_history`) + **percentile analysis** on top of the shared engines/metrics.

**Architecture — engines vs metrics (both live in calculations/):**
- **Engines** (in [`calculations/engines/`](calculations/ARCHITECTURE.md)) — one per raw quantity. Self-register via `register_engine()`. Auto-discovered by the central `_registry.py`. Engines are leaves: they never import each other or metrics. 18 engines in 7 categories.
  - `price.py` — COTAHIST daily close
  - `earnings.py` — DFP + ITR TTM earnings derivation
  - `shares.py` — FRE shares outstanding (+ investsite fallback)
  - `pl.py` — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
  - `dividends.py` — B3 cash_dividends DPA TTM
  - `revenue.py`, `gross_profit.py`, `ebit.py`, `tax.py` — DRE TTM flows
  - `assets.py`, `total_assets.py`, `cash.py` — BPA snapshots
  - `debt.py`, `current_liabilities.py` — BPP snapshots
  - `da.py`, `capex.py` — DFC description-based TTM search engines
- **Metrics** (in [`calculations/metrics/`](calculations/ARCHITECTURE.md)) — one per ratio. Self-register via `register_metric()`. Auto-discovered by the central `_registry.py`. 21 metrics in 2 types: 8 per-share+ratio (Type 1) + 13 fundamental ratio (Type 2).
  - `lpa.py` — LPA (earnings/shares) + P/L (price/LPA)
  - `vpa.py` — VPA (pl/shares) + P/VPA (price/VPA)
  - `dpa.py` — DPA (dividends TTM) + Div Yield (DPA/price) + Payout (DPA/LPA)
  - `rps.py` — RPS (revenue/shares) + PSR (price/RPS)
  - `ev_ebitda.py` — EBITDA/Ação + EV/EBITDA (6 engines, most complex)
  - `roe.py`, `roa.py`, `roic.py` — Returns (fundamental ratios)
  - `gross_margin.py`, `operating_margin.py`, `net_margin.py`, `ebitda_margin.py` — Margins
  - `debt_equity.py`, `net_debt_ebitda.py` — Leverage
  - `asset_turnover.py`, `capex_revenue.py`, `current_ratio.py` — Other fundamentals

**Each metric produces both:**
- A **per-share value** (LPA, VPA, DPA) — useful on its own (e.g., backtest filters on EPS)
- A **price ratio** (P/L, P/VPA, Div Yield) — tells you if the stock is cheap vs history
- Optional **bonus ratios** (e.g., Payout = DPA/LPA) — included in the series + summary

**Key characteristics:**
- **Thin wrapper over calculations/** — engines, metrics, and the registry moved to `skills/cvm/calculations/` in v2.2 (Phase 1 refactor). Historical adds mode dispatch + percentile analysis on top.
- **Central auto-discovery (in calculations/)** — `_registry.py` lives at the calculations top level, globs both `engines/*.py` and `metrics/*.py`. Adding a metric = drop a file + `register_metric()`. Everything else auto-generates.
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`. Consistent pattern.
- **Step-function optimization** — price changes daily, PL/earnings change quarterly, shares change annually, dividends change on payment dates. Precompute step functions, do O(1) lookups per day.
- **Percentile analysis** — "PETR4 is at 25th percentile of its 5Y P/L range" = cheap vs history (owned by historical, NOT calculations)
- **Dual-dataset charts (Type 1) vs single-dataset (Type 2)** — each Type 1 metric chart shows BOTH the per-share value AND the ratio; each Type 2 metric chart shows only the fundamental ratio.
- **Backtest foundation** — calculations engines/ are standalone modules importable by a future backtest skill.
- **Data range** — P/L: 2012+ (need 2 years of ITR for TTM). P/VPA: 2010+ (DFP only). Div Yield: depends on B3 dividends data (varies per ticker). COTAHIST prices from 2010.

---

## 🚀 Quick Start

```
# 5-year LPA + P/L history (daily series, dual-dataset chart)
skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')

# 5-year VPA + P/VPA history
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# 5-year DPA + Div Yield + Payout history
skill(domain="cvm", sub_domain="historical", mode="dpa_history", params='{"company":"PETR4","months":60}')

# Summary: current ratio vs 1Y/3Y/5Y average + percentile (includes per-share value)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"dpa"}')

# Generic ratio history (accepts aliases: pe/pl/p/l → lpa; pvpa/p/vpa → vpa; dy/yld/payout → dpa)
skill(domain="cvm", sub_domain="historical", mode="ratio_history", params='{"company":"PETR4","metric":"dy"}')
```

---

## 🔄 When to Use vs Alternatives

| Need | Mode | Why |
|------|------|-----|
| Is PETR4 cheap vs its own history? | `summary(metric="lpa")` | Current P/L + percentile + interpretation |
| P/L over time (chart) | `lpa_history` | Daily series, dual-dataset (LPA + P/L) |
| P/VPA over time (chart) | `vpa_history` | Daily series, dual-dataset (VPA + P/VPA) |
| Dividend Yield over time (chart) | `dpa_history` | Daily series, dual-dataset (DPA + Div Yield) |
| Compare P/L, P/VPA, Div Yield | Run multiple `summary(metric=...)` calls | One per metric, compare results |
| Any metric, generic dispatch | `ratio_history(metric=...)` | Accepts canonical names + aliases |
| Just the per-share value (LPA, VPA, DPA)? | Import metric directly: `from skills.cvm.calculations.metrics.lpa import lpa_at` | For backtests / custom analysis (engine/metric lives in calculations) |

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/b3/cotahist` synced (daily prices, 2010-present)
- `data_sources/b3/dividends` synced (cash dividends per ticker — needed for DPA/Div Yield/Payout)
- `data_sources/cvm/dfp` synced (annual earnings + PL snapshots)
- `data_sources/cvm/itr` synced (quarterly cumulative earnings + PL snapshots, 2011-present)
- `data_sources/cvm/fre` synced (shares outstanding — may be empty; investsite fallback used)
- `data_sources/cvm/bridge` synced (ticker → CNPJ resolution)

---

## 📊 Rendering & Export

```
# LPA + P/L chart (dual-dataset line chart)
report(action="chart", title="PETR4 LPA + P/L History",
       data=<lpa_history JSON>, config={"chart_type":"line","adapter":"historical_lpa_chart"})

# VPA + P/VPA chart (dual-dataset line chart)
report(action="chart", title="PETR4 VPA + P/VPA History",
       data=<vpa_history JSON>, config={"chart_type":"line","adapter":"historical_vpa_chart"})

# DPA + Div Yield chart (dual-dataset line chart)
report(action="chart", title="PETR4 DPA + Div Yield History",
       data=<dpa_history JSON>, config={"chart_type":"line","adapter":"historical_dpa_chart"})

# Summary table (metric-aware: shows per-share + ratio + components)
report(action="table", title="PETR4 Summary",
       data=<summary JSON>, config={"adapter":"historical_summary"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [CALCULATIONS.md](CALCULATIONS.md) | Shared engine + metric library (18 engines + 21 metrics) |
| [ARCHITECTURE.md](historical/ARCHITECTURE.md) | Historical architecture — thin wrapper over calculations, mode dispatch, percentile analysis, testing |
| [API.md](historical/API.md) | All historical modes (auto-generated), error cases, report adapters. Engine/metric/registry API: see [calculations/API.md](calculations/API.md) |
| [CHANGELOG.md](historical/CHANGELOG.md) | Version history + roadmap (backtest) |
| [INSTRUCTIONS.md](historical/INSTRUCTIONS.md) | AI editing rules for the historical skill (engine/metric rules: see calculations/INSTRUCTIONS.md) |

**Related:**
| File | Purpose |
|------|---------|
| [CALCULATIONS.md](CALCULATIONS.md) | Overview of the shared calculations package (engines + metrics + registry) |
| [calculations/ARCHITECTURE.md](calculations/ARCHITECTURE.md) | Central registry design, engine/metric pattern, auto-discovery, TTM/snapshot/multi-code/description-search algorithms |
| [calculations/API.md](calculations/API.md) | All 18 engine function signatures + all 21 metric function signatures + registry API |
| [calculations/INSTRUCTIONS.md](calculations/INSTRUCTIONS.md) | AI editing rules for engines/metrics/registry |

---

*Last updated: 2026-07-26 (v2.2 — Phase 1 refactor: engines + metrics + registry extracted to calculations/; historical now a thin wrapper).*
