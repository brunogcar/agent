<- Back to [CVM Data Sources](../CVM.md)

# 📊 CGVN — Código de Governança e Melhores Práticas

CGVN contains governance practice disclosures — companies report which recommended practices they adopt (Sim/Não/Parcialmente).

**Key characteristics:**
- **2 tables** — cgvn_documents (filing metadata) + cgvn_practices (practices with adoption status)
- **Governance scoring** — % of recommended practices adopted, partial, not adopted
- **Read-only** — query + status modes only
- **SQLite** — `memory_db/cvm/cgvn.db`

---

## 🚀 Quick Start

```powershell
# Sync single year
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cgvn.sync_engine import sync; print(sync(year=2025))"

# Sync full history
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cgvn.sync_engine import sync; print(sync(full_history=True))"

# Query governance score
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cgvn.query_engine import query; print(query(company='PETR4', score=True))"
```

Or via MCP tool:
```
data_source(domain='cvm', sub_domain='cgvn', mode='sync', params='{"year":2025}')
data_source(domain='cvm', sub_domain='cgvn', mode='query', params='{"company":"PETR4","score":true}')
```

---

## 📊 Governance Skill

See [Governance Skill](../../skills/cvm/GOVERNANCE.md) for the analytical skill.

---

*Last updated: 2026-07-25 (v1.0).*

