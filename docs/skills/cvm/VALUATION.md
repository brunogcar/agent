<- Back to [CVM Skills](../CVM.md)

# 💰 VALUATION — Valuation Ratios Skill

Computes valuation ratios from local data: b3 price + CVM DFP financials + FRE shares. The "investsite goldmine" — but computed from our own databases instead of scraped.

**Key characteristics:**
- **Combines 3 data sources** — b3/api (trades.db price) + cvm/dfp (financials) + cvm/fre (shares outstanding) + cvm/bridge (ticker resolution)
- **7 ratios computed** — P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap
- **Underlying values included** — each ratio returns the inputs (price, EPS, VPA, etc.) so callers can verify
- **Data source status** — `summary` mode shows which DBs are synced vs missing
- **Uses core/br_validator** — `validate_ticker()`, `parse_escala()` for consistent parsing
- **Read-only** — no sync. Assumes b3 trades.db + dfp.db + fre.db are already synced.

---

## 🚀 Quick Start

```
# All valuation ratios
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')

# Ratios + data source availability
skill(domain="cvm", sub_domain="valuation", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/b3/api` synced (trades table — latest price)
- `data_sources/cvm/dfp` synced (annual financials)
- `data_sources/cvm/fre` synced (distribuicao_capital — shares outstanding)
- `data_sources/cvm/bridge` synced (ticker → CNPJ)

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](valuation/ARCHITECTURE.md) | Ratio formulas, data flow, data source requirements |
| [API.md](valuation/API.md) | 2 modes: ratios, summary |
| [CHANGELOG.md](valuation/CHANGELOG.md) | Version history + roadmap |
| [INSTRUCTIONS.md](valuation/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-24 (v1.0).*
