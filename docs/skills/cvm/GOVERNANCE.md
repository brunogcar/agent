<- Back to [CVM Skills](../CVM.md)

# ⚖️ GOVERNANCE — Governance Practices Analysis Skill

The `governance` skill analyzes CGVN disclosures — which recommended governance practices companies adopt.

**Key characteristics:**
- **4 modes** — practices (all practices), score (% adopted), by_chapter (grouped by chapter), dashboard (multi-tab overview)
- **Read-only** — calls cgvn.query_engine directly
- **Bridge auto-sync** — first ticker query auto-syncs the bridge
- **Data freshness** — includes data_freshness field
- **Modular layout (v1.1)** — `_registry.py` + `modes/` (4 mode files) + `report.py` auto-discovered via `@register_mode`. Mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends` modular pattern.

---

## 🚀 Quick Start

```
skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="practices", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="by_chapter", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="dashboard", params='{"company":"PETR4"}')
```

---

## 📊 Rendering & Export

```
report(action="table", title="PETR4 Governance", data=<governance JSON>, config={"adapter":"governance_score"})
report(action="dashboard", title="PETR4 Governance Dashboard", data=<governance dashboard JSON>, config={"adapter":"governance_dashboard"})
```

---

*Last updated: 2026-07-29 (v1.1 — modular split + dashboard mode).*

