<- Back to [CVM Skills](../CVM.md)

# 📈 HISTORICAL — Historical Financial Ratios Skill

Computes financial ratios (P/L, P/VPA) over time by combining **engines** (basics: price, earnings, shares, PL) into **metrics** (ratios: pe, vpa). Tells you if a stock is cheap vs its **own history**.

**Architecture — engines vs metrics:**
- **Engines** (`engines/`) — one per raw quantity. Each engine fetches ONE basic number at any historical date from its data source(s). Engines are leaves: they never import each other or metrics.
  - `price.py` — COTAHIST daily close
  - `earnings.py` — DFP + ITR TTM earnings derivation
  - `shares.py` — FRE shares outstanding (+ investsite fallback)
  - `pl.py` — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
- **Metrics** (`metrics/`) — one per ratio. A metric imports 2+ engines and combines them. Metrics NEVER query CVM/B3 directly.
  - `pe.py` — P/L = price / (TTM earnings / shares)
  - `vpa.py` — P/VPA = price / (PL / shares)

**Key characteristics:**
- **TTM earnings engine** — derives trailing twelve months earnings at any historical date using DFP annual + ITR quarterly cumulative data
- **PL snapshot engine** — balance sheet is point-in-time (no TTM derivation needed); finds most recent BPP snapshot <= date
- **Step-function optimization** — price changes daily, PL/earnings change quarterly, shares change annually. Precompute step functions, do O(1) lookups per day.
- **Percentile analysis** — "PETR4 is at 25th percentile of its 5Y P/L range" = cheap vs history
- **4 modes** — pe_history, vpa_history, ratio_history, summary
- **Backtest foundation** — engines/ are standalone modules importable by a future backtest skill
- **Data range** — P/L: 2012+ (need 2 years of ITR for TTM). P/VPA: 2010+ (DFP only). COTAHIST prices from 2010.

---

## 🚀 Quick Start

```
# 5-year P/L history (daily series)
skill(domain="cvm", sub_domain="historical", mode="pe_history", params='{"company":"PETR4","months":60}')

# 5-year P/VPA history (daily series)
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# Summary: current P/L vs 1Y/3Y/5Y average + percentile
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')

# Summary for P/VPA metric
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')
```

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
# P/L chart (line chart over time)
report(action="chart", title="PETR4 P/L History",
       data=<historical pe_history JSON>, config={"chart_type":"line","adapter":"historical_pe_chart"})

# P/VPA chart (line chart over time)
report(action="chart", title="PETR4 P/VPA History",
       data=<historical vpa_history JSON>, config={"chart_type":"line","adapter":"historical_vpa_chart"})

# Summary table (metric-aware: works for both pe and vpa)
report(action="table", title="PETR4 P/L Summary",
       data=<historical summary JSON>, config={"adapter":"historical_summary"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](historical/ARCHITECTURE.md) | Engine vs metric pattern, TTM algorithm, step-function design, how to add new engines/metrics |
| [API.md](historical/API.md) | 4 modes: pe_history, vpa_history, ratio_history, summary |
| [CHANGELOG.md](historical/CHANGELOG.md) | Version history + roadmap (ev_ebitda, psr, dividend yield, backtest) |
| [INSTRUCTIONS.md](historical/INSTRUCTIONS.md) | AI editing rules — engine vs metric separation, NEVER DO, ALWAYS DO |

---

*Last updated: 2026-07-26 (v1.1 — added PL engine + VPA metric).*
