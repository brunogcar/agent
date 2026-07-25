<- Back to [CVM Skills](../CVM.md)

# ⚖️ GOVERNANCE — Governance Practices Analysis Skill

The `governance` skill analyzes CGVN disclosures — which recommended governance practices companies adopt.

**Key characteristics:**
- **3 modes** — practices (all practices), score (% adopted), by_chapter (grouped by chapter)
- **Read-only** — calls cgvn.query_engine directly
- **Bridge auto-sync** — first ticker query auto-syncs the bridge
- **Data freshness** — includes data_freshness field

---

## 🚀 Quick Start

```
skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="practices", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="by_chapter", params='{"company":"PETR4"}')
```

---

## 📊 Rendering & Export

```
report(action="table", title="PETR4 Governance", data=<governance JSON>, config={"adapter":"governance_score"})
```

---

*Last updated: 2026-07-25 (v1.0).*

