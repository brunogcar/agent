<- Back to [CVM Skills](../CVM.md)

# 🔍 INSIDER — Insider Trading Analysis Skill

The `insider` skill analyzes VLMO disclosures — when directors, officers, or controlling shareholders buy or sell company securities.

**Key characteristics:**
- **4 modes** — history (recent transactions), by_role (grouped by role), summary (net buy/sell per month + sentiment), dashboard (multi-tab composition for the report tool)
- **Modular layout (v1.1)** — split into `_registry.py` + `modes/{history,by_role,summary,dashboard}.py` + `report.py`. Auto-discovery via `@register_mode`.
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

# Multi-tab dashboard (Overview + Recent Transactions + By Role + Monthly Net)
report(action="dashboard", title="PETR4 Insider Dashboard",
       data=<insider dashboard JSON>, config={"adapter":"insider_dashboard"})
```

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](insider/ARCHITECTURE.md) | Data flow, sentiment computation |
| [API.md](insider/API.md) | 4 modes: history, by_role, summary, dashboard |
| [CHANGELOG.md](insider/CHANGELOG.md) | Version history |
| [ROADMAP.md](insider/ROADMAP.md) | Backlog + priorities |
| [INSTRUCTIONS.md](insider/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-08-04 (v1.2 — dashboard overhaul with sidebar groups + company header + price chart + freshness footer; see CHANGELOG.md).*
