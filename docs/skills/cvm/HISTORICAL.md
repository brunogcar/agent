<- Back to [CVM Skills](../CVM.md)

# 📈 HISTORICAL — Historical Financial Ratios Skill

Computes financial ratios (P/L, P/VPA, EV/EBITDA) over time by combining COTAHIST daily prices + DFP/ITR TTM earnings + FRE shares outstanding. Tells you if a stock is cheap vs its **own history**.

**Key characteristics:**
- **TTM earnings engine** — derives trailing twelve months earnings at any historical date using DFP annual + ITR quarterly cumulative data
- **Daily P/L series** — price changes daily, earnings change quarterly, shares change annually
- **Percentile analysis** — "PETR4 is at 25th percentile of its 5Y P/L range" = cheap vs history
- **3 modes** — pe_history (daily series), ratio_history (any metric), summary (current vs averages)
- **Backtest foundation** — engines/ are standalone modules importable by a future backtest skill
- **Data range** — 2012 onwards (need 2 years of ITR for TTM derivation). COTAHIST prices from 2010.

---

## 🚀 Quick Start

```
# 5-year P/L history (daily series)
skill(domain="cvm", sub_domain="historical", mode="pe_history", params='{"company":"PETR4","months":60}')

# Summary: current P/L vs 1Y/3Y/5Y average + percentile
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/b3/cotahist` synced (daily prices, 2010-present)
- `data_sources/cvm/dfp` synced (annual earnings)
- `data_sources/cvm/itr` synced (quarterly cumulative earnings, 2011-present)
- `data_sources/cvm/fre` synced (shares outstanding)
- `data_sources/cvm/bridge` synced (ticker → CNPJ resolution)

---

## 📊 Rendering & Export

```
report(action="chart", title="PETR4 P/L History",
       data=<historical pe_history JSON>, config={"chart_type":"line","adapter":"historical_pe_chart"})

report(action="table", title="PETR4 P/L Summary",
       data=<historical summary JSON>, config={"adapter":"historical_summary"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](historical/ARCHITECTURE.md) | TTM algorithm, engine design, metric composition, how to add new metrics |
| [API.md](historical/API.md) | 3 modes: pe_history, ratio_history, summary |
| [CHANGELOG.md](historical/CHANGELOG.md) | Version history + roadmap (pvpa, ev_ebitda, backtest) |
| [INSTRUCTIONS.md](historical/INSTRUCTIONS.md) | AI editing rules — how to add metrics/engines |

---

*Last updated: 2026-07-25 (v1.0).*
