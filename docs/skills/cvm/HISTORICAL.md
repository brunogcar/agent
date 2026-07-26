<- Back to [CVM Skills](../CVM.md)

# 📈 HISTORICAL — Historical Financial Ratios Skill

Computes financial ratios over time by combining **engines** (basics: price, earnings, shares, PL) into **metrics** (per-share values + price ratios: LPA+P/L, VPA+P/VPA). Tells you if a stock is cheap vs its **own history**.

**This skill is the pattern template** for other skills that need auto-discovery + registry architecture. The engine/metric separation, auto-discovery via glob+importlib, and MetricSpec registry are designed to be copied.

**Architecture — engines vs metrics:**
- **Engines** (`engines/`) — one per raw quantity. Auto-discovered at import time via glob+importlib. Engines are leaves: they never import each other or metrics.
  - `price.py` — COTAHIST daily close
  - `earnings.py` — DFP + ITR TTM earnings derivation
  - `shares.py` — FRE shares outstanding (+ investsite fallback)
  - `pl.py` — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
- **Metrics** (`metrics/`) — one per ratio. Auto-discovered + self-registered via `@register_metric`. Each metric produces BOTH a per-share value AND a price ratio.
  - `lpa.py` — LPA (earnings/shares) + P/L (price/LPA)
  - `vpa.py` — VPA (pl/shares) + P/VPA (price/VPA)

**Each metric produces both:**
- A **per-share value** (LPA, VPA) — useful on its own (e.g., backtest filters on EPS)
- A **price ratio** (P/L, P/VPA) — tells you if the stock is cheap vs history

**Key characteristics:**
- **Auto-discovery** — drop a metric file in `metrics/` + `register_metric()`. The `<metric>_history` mode, chart adapter, and dispatch all auto-generate. No edits to `__init__.py` or `historical.py`.
- **Step-function optimization** — price changes daily, PL/earnings change quarterly, shares change annually. Precompute step functions, do O(1) lookups per day.
- **Percentile analysis** — "PETR4 is at 25th percentile of its 5Y P/L range" = cheap vs history
- **Dual-dataset charts** — each metric chart shows BOTH the per-share value AND the ratio
- **Backtest foundation** — engines/ are standalone modules importable by a future backtest skill
- **Data range** — P/L: 2012+ (need 2 years of ITR for TTM). P/VPA: 2010+ (DFP only). COTAHIST prices from 2010.

---

## 🚀 Quick Start

```
# 5-year LPA + P/L history (daily series, dual-dataset chart)
skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')

# 5-year VPA + P/VPA history (daily series, dual-dataset chart)
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# Summary: current P/L vs 1Y/3Y/5Y average + percentile (includes LPA per-share value)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')

# Summary for P/VPA metric (includes VPA per-share value)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')

# Generic ratio history (accepts aliases: pe, pl, p/l → lpa; pvpa, p/vpa → vpa)
skill(domain="cvm", sub_domain="historical", mode="ratio_history", params='{"company":"PETR4","metric":"pe"}')
```

---

## 🔄 When to Use vs Alternatives

| Need | Mode | Why |
|------|------|-----|
| Is PETR4 cheap vs its own history? | `summary(metric="lpa")` | Current P/L + percentile + interpretation |
| P/L over time (chart) | `lpa_history` | Daily series, dual-dataset (LPA + P/L) |
| P/VPA over time (chart) | `vpa_history` | Daily series, dual-dataset (VPA + P/VPA) |
| Compare P/L and P/VPA side by side | Run both `summary(metric="lpa")` + `summary(metric="vpa")` | Two calls, compare results |
| Any metric, generic dispatch | `ratio_history(metric=...)` | Accepts canonical names + aliases |
| Just the per-share value (LPA, VPA)? | Import engine directly: `from skills.cvm.historical.metrics.lpa import lpa_at` | For backtests / custom analysis |

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/b3/cotahist` synced (daily prices, 2010-present)
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

# Summary table (metric-aware: shows per-share + ratio + components)
report(action="table", title="PETR4 Summary",
       data=<summary JSON>, config={"adapter":"historical_summary"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](historical/ARCHITECTURE.md) | Engine/metric pattern, auto-discovery, registry design, TTM/PL algorithms, how to add engines/metrics |
| [API.md](historical/API.md) | 4 modes (auto-generated), engine API, metric API, report adapters, error cases |
| [CHANGELOG.md](historical/CHANGELOG.md) | Version history + roadmap (ev_ebitda, psr, backtest) |
| [INSTRUCTIONS.md](historical/INSTRUCTIONS.md) | AI editing rules — engine/metric separation, auto-discovery, registry, NEVER DO, ALWAYS DO |

---

*Last updated: 2026-07-26 (v1.2 — auto-discovery + registry + per-share-and-ratio pattern).*
