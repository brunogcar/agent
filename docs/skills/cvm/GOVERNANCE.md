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

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [CHANGELOG.md](governance/CHANGELOG.md) | Version history |
| [ROADMAP.md](governance/ROADMAP.md) | Backlog + priorities |
| [INSTRUCTIONS.md](governance/INSTRUCTIONS.md) | AI editing rules |

---

*Last updated: 2026-08-04 (v1.2 — dashboard overhaul with sidebar groups + company header + price chart + freshness footer; see CHANGELOG.md).*

