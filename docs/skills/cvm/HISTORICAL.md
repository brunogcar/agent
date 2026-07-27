<- Back to [CVM Skills](../CVM.md)

# 📈 HISTORICAL — Historical Financial Ratios Skill

Computes financial ratios over time by combining **engines** (basics: price, earnings, shares, PL, dividends) into **metrics** (per-share values + price ratios: LPA+P/L, VPA+P/VPA, DPA+Div Yield+Payout). Tells you if a stock is cheap vs its **own history**.

**This skill is the pattern template** for other skills that need auto-discovery + registry architecture. The central `_registry.py`, engine/metric separation, and self-registration pattern are designed to be copied.

**Architecture — engines + metrics in [calculations/](CALCULATIONS.md):**
- **Engines** (`engines/`) — one per raw quantity. Self-register via `register_engine()`. Auto-discovered by the central `_registry.py`. Engines are leaves: they never import each other or metrics.
  - `price.py` — COTAHIST daily close
  - `earnings.py` — DFP + ITR TTM earnings derivation
  - `shares.py` — FRE shares outstanding (+ investsite fallback)
  - `pl.py` — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
  - `dividends.py` — B3 cash_dividends DPA TTM
  - `revenue.py` — DFP + ITR DRE 3.01 TTM net revenue
  - (roe uses earnings + pl, no new engine)
- **Metrics** (`metrics/`) — one per ratio. Self-register via `register_metric()`. Auto-discovered by the central `_registry.py`. Each metric produces BOTH a per-share value AND a price ratio (+ optional bonus ratios).
  - `lpa.py` — LPA (earnings/shares) + P/L (price/LPA)
  - `vpa.py` — VPA (pl/shares) + P/VPA (price/VPA)
  - `dpa.py` — DPA (dividends TTM) + Div Yield (DPA/price) + Payout (DPA/LPA)
  - `rps.py` — RPS (revenue/shares) + PSR (price/RPS)
  - `roe.py` — ROE (earnings/PL, fundamental ratio — no price or shares)

**Each metric produces both:**
- A **per-share value** (LPA, VPA, DPA) — useful on its own (e.g., backtest filters on EPS)
- A **price ratio** (P/L, P/VPA, Div Yield) — tells you if the stock is cheap vs history
- Optional **bonus ratios** (e.g., Payout = DPA/LPA) — included in the series + summary

**Key characteristics:**
- **Central auto-discovery** — `_registry.py` lives at the skill top level, globs both `engines/*.py` and `metrics/*.py`. Adding a metric = drop a file + `register_metric()`. Everything else auto-generates.
- **Both layers self-register** — engines via `register_engine(EngineSpec(...))`, metrics via `register_metric(MetricSpec(...))`. Consistent pattern.
- **Step-function optimization** — price changes daily, PL/earnings change quarterly, shares change annually, dividends change on payment dates. Precompute step functions, do O(1) lookups per day.
- **Percentile analysis** — "PETR4 is at 25th percentile of its 5Y P/L range" = cheap vs history
- **Dual-dataset charts** — each metric chart shows BOTH the per-share value AND the ratio
- **Backtest foundation** — engines/ are standalone modules importable by a future backtest skill
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
| Just the per-share value (LPA, VPA, DPA)? | Import engine directly: `from skills.cvm.calculations.metrics.lpa import lpa_at` | For backtests / custom analysis |

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
| [CALCULATIONS.md](CALCULATIONS.md) | Shared engine + metric library (16 engines + 17 metrics) — landing page |
| [calculations/ARCHITECTURE.md](calculations/ARCHITECTURE.md) | Engine/metric pattern, central auto-discovery, categories, algorithms (TTM, snapshot, description-search, multi-code sum), dependency graph, how-to guides, testing |
| [calculations/API.md](calculations/API.md) | All 16 engine signatures + 17 metric signatures + registry API + error handling |
| [calculations/INSTRUCTIONS.md](calculations/INSTRUCTIONS.md) | Engine/metric AI editing rules — NEVER DO, ALWAYS DO, naming convention, anti-patterns v1.2–v1.9, pattern template checklist |
| [historical/ARCHITECTURE.md](historical/ARCHITECTURE.md) | Mode dispatch flow, MANIFEST auto-generation, percentile analysis, summary interpretation, testing |
| [historical/API.md](historical/API.md) | All modes (auto-generated `<metric>_history`, generic `ratio_history`, generic `summary`), report adapters, error cases |
| [historical/CHANGELOG.md](historical/CHANGELOG.md) | Version history (v1.0 → v2.2 — Phase 1 extraction to calculations) |
| [historical/INSTRUCTIONS.md](historical/INSTRUCTIONS.md) | Historical-skill-specific AI editing rules — never edit MANIFEST, never edit adapters, mode dispatch rules |

---

*Last updated: 2026-07-26 (v2.2).*
