<- Back to [CVM Skills](../CVM.md)

# 🔍 INSIDER — Insider Trading Analysis Skill

The `insider` skill analyzes VLMO disclosures — when directors, officers, or controlling shareholders buy or sell company securities.

**Key characteristics:**
- **3 modes** — history (recent transactions), by_role (grouped by role), summary (net buy/sell per month + sentiment)
- **Read-only** — calls vlmo.query_engine directly
- **Bridge auto-sync** — first ticker query auto-syncs the bridge
- **Data freshness** — includes data_freshness field showing last sync timestamps

---

## 🚀 Quick Start

```
# Recent insider transactions
skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')

# By role (directors vs officers vs shareholders)
skill(domain="cvm", sub_domain="insider", mode="by_role", params='{"company":"PETR4"}')

# Monthly net buy/sell + sentiment
skill(domain="cvm", sub_domain="insider", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/cvm/vlmo` synced (vlmo.db)
- `data_sources/cvm/bridge` synced (auto-syncs on ticker query)

---

## 📊 Rendering & Export

```
report(action="table", title="PETR4 Insider",
       data=<insider JSON>, config={"adapter":"insider_history"})
report(action="table", title="PETR4 Insider Summary",
       data=<insider summary JSON>, config={"adapter":"insider_summary"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](insider/ARCHITECTURE.md) | Data flow, sentiment computation |
| [API.md](insider/API.md) | 3 modes: history, by_role, summary |
| [CHANGELOG.md](insider/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](insider/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-07-25 (v1.0).*
